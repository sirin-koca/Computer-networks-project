# DATA2410 - PORTFOLIO2:

# Import required libraries
import argparse
import socket
import struct
import sys
import os

# DRTP header format
header_format = '!IIHH'

# Constants
HEADER_SIZE = 12
DATA_SIZE = 1460
PACKET_SIZE = HEADER_SIZE + DATA_SIZE
TIMEOUT = 0.5
WINDOW_SIZE = 64


def parse_flags(flags):
    syn = flags & (1 << 3)
    ack = flags & (1 << 2)
    fin = flags & (1 << 1)
    return syn, ack, fin


# Handling command line arguments: this function will take user input and parse them using the "argparse" module:
def argument_parser():
    parser = argparse.ArgumentParser(description='UDP file transfer with reliability layer')
    parser.add_argument('-c', '--client', action='store_true', help='Start the application as a client')
    parser.add_argument('-s', '--server', action='store_true', help='Start the application as a server')
    parser.add_argument('-i', '--IP', type=str, help='IP to connect', default='127.0.0.1')
    parser.add_argument('-p', '--port', type=int, help='port to connect to or bind to (default: 5000)', default=5000)
    parser.add_argument('-f', '--file', help='The path to the file to send or receive')
    parser.add_argument('-b', '--buffer_size', type=int, default=2048, help='Buffer size')
    parser.add_argument('-t', '--timeout', type=int, default=5, help='Timeout in seconds')
    parser.add_argument('-r', '--reliability', choices=['stop_and_wait', 'gbn', 'sr'], required=True,
                        help='Reliability method: stop_and_wait, gbn, or sr')
    parser.add_argument('--test', type=str, choices=['skipack', 'loss'], help='Test case: skipack or loss')

    args = parser.parse_args()

    if args.server and not args.ip_address:
        parser.error("Server mode requires the -i/--ip_address flag")

    if args.client and not args.file:
        parser.error("Client mode requires the -f/--file flag")

    return args


# DRTP functions: the DRTP header structure using the 'struct' module:
def create_header(seq_num, ack_num, flags, window):
    return struct.pack('!IIHH', seq_num, ack_num, flags, window)


def parse_header(packet):
    header = packet[:HEADER_SIZE]
    fields = struct.unpack('!IIHH', header)
    return fields


def create_packet(header, data):
    return header + data


def parse_packet(packet):
    header = packet[:HEADER_SIZE]
    data = packet[HEADER_SIZE:]
    return header, data


def send_packet(sock, addr, seq_num, ack_num, flags, data):
    header = create_header(seq_num, ack_num, flags, len(data))  # it should be window size instead of len(data)
    packet = create_packet(header, data)
    sock.sendto(packet, addr)


def receive_packet(sock):
    try:
        packet, addr = sock.recvfrom(PACKET_SIZE)
        header, data = parse_packet(packet)
        seq_num, ack_num, flags, _ = parse_header(header)
        return seq_num, ack_num, flags, data, addr
    except socket.timeout:
        return None, None, None, None, None
    except socket.error as e:
        return None, None, None, None, f"Socket error: {e}"
    except Exception as e:
        return None, None, None, None, f"Unexpected error: {e}"


def establish_connection(sock, addr):
    syn_flag = 1 << 3
    send_packet(sock, addr, 0, 0, syn_flag, b'')
    sock.settimeout(TIMEOUT)
    seq_num, ack_num, flags, _, _ = receive_packet(sock)
    sock.settimeout(None)
    if flags is not None:
        if parse_flags(flags)[0]:  # Check if SYN flag is set in the response
            # Connection established
            return True
        else:
            # Error: SYN flag not set in the response
            return False, "Error: SYN flag not set in the response"
    else:
        # Error: packet lost or corrupted
        return False, "Error: Failed to receive response"


def teardown_connection(sock, addr):
    fin_flag = 1 << 1
    send_packet(sock, addr, 0, 0, fin_flag, b'')
    seq_num, ack_num, flags, _, _ = receive_packet(sock)
    if flags is not None:
        if parse_flags(flags)[2]:  # Check if FIN flag is set in the response
            return True
        else:
            # Error: FIN flag not set in the response
            return False, "Error: FIN flag not set in the response"
    else:
        # Error: packet lost or corrupted
        return False, "Error: Failed to receive response"


# Reliable methods using 'socket' module
def stop_and_wait(sock, sender, receiver, file):
    if sender:  # If the application is running as the sender
        success, err_msg = establish_connection(sock, receiver)
        if not success:
            return False, err_msg
        with open(file, 'rb') as file:
            seq_num = 0
            while True:
                data = file.read(DATA_SIZE)
                if not data:
                    break

                # Send the packet and wait for acknowledgment
                while True:
                    try:
                        send_packet(sock, receiver, seq_num, 0, 0, data)
                        sock.settimeout(TIMEOUT)
                        _, ack_num, _, _, _ = receive_packet(sock)
                        sock.settimeout(None)
                        if ack_num == seq_num:
                            break
                    except socket.timeout:
                        # Timeout: retransmit packet
                        continue
                    except socket.error as e:
                        return False, f"Socket error: {e}"
                    except Exception as e:
                        return False, f"Unexpected error: {e}"

                # Toggle the sequence number
                seq_num = 1 - seq_num

    elif receiver:  # If the application is running as the receiver
        success, err_msg = teardown_connection(sock, sender)
        if not success:
            return False, err_msg
        with open(file, 'wb') as file:
            expected_seq_num = 0
            while True:
                seq_num, _, _, data, _ = receive_packet(sock)
                if seq_num == expected_seq_num:
                    file.write(data)

                    # Toggle the expected sequence number
                    expected_seq_num = 1 - expected_seq_num

                # Send acknowledgment
                try:
                    send_packet(sock, sender, 0, seq_num, 0, b'')
                except socket.error as e:
                    return False, f"Socket error: {e}"
                except Exception as e:
                    return False, f"Unexpected error: {e}"

    return True, None


def go_back_n(sock, sender, receiver, file, window_size):
    if sender:
        with open(file, 'rb') as file:
            base = 0
            next_seq_num = 0
            buffer = []

            while True:
                # Fill the buffer
                while next_seq_num < base + window_size and (not buffer or buffer[-1]):
                    data = file.read(DATA_SIZE)
                    buffer.append(data)
                    if data:
                        try:
                            send_packet(sock, receiver, next_seq_num, 0, 0, data)
                        except socket.error as e:
                            return False, f"Socket error: {e}"
                        except Exception as e:
                            return False, f"Unexpected error: {e}"
                        next_seq_num += 1

                # Wait for acknowledgments
                try:
                    _, ack_num, _, _, _ = receive_packet(sock)
                    base = ack_num + 1
                except socket.timeout:
                    # Timeout: retransmit packets from base to next_seq_num
                    for i in range(base, next_seq_num):
                        try:
                            send_packet(sock, receiver, i, 0, 0, buffer[i - base])
                        except socket.error as e:
                            return False, f"Socket error: {e}"
                        except Exception as e:
                            return False, f"Unexpected error: {e}"
                except socket.error as e:
                    return False, f"Socket error: {e}"
                except Exception as e:
                    return False, f"Unexpected error: {e}"

                if not buffer[0]:
                    break

    elif receiver:
        with open(file, 'wb') as file:
            expected_seq_num = 0

            while True:
                seq_num, _, _, data, _ = receive_packet(sock)
                if seq_num == expected_seq_num:
                    file.write(data)
                    expected_seq_num += 1

                # Send acknowledgment
                try:
                    send_packet(sock, sender, 0, seq_num, 0, b'')
                except socket.error as e:
                    return False, f"Socket error: {e}"
                except Exception as e:
                    return False, f"Unexpected error: {e}"

                if not data:
                    break

    return True, None


def selective_repeat(sock, sender, receiver, file, window_size):
    if sender:
        with open(file, 'rb') as file:
            base = 0
            next_seq_num = 0
            buffer = []
            acked_packets = set()

            while True:
                # Fill the buffer
                while next_seq_num < base + window_size and (not buffer or buffer[-1]):
                    data = file.read(DATA_SIZE)
                    buffer.append(data)
                    if data:
                        try:
                            send_packet(sock, receiver, next_seq_num, 0, 0, data)
                        except socket.error as e:
                            return False, f"Socket error: {e}"
                        except Exception as e:
                            return False, f"Unexpected error: {e}"
                        next_seq_num += 1

                # Wait for acknowledgments
                try:
                    _, ack_num, _, _, _ = receive_packet(sock)
                    if ack_num is not None:
                        acked_packets.add(ack_num)

                    # Slide the window
                    while base in acked_packets:
                        buffer.pop(0)
                        base += 1
                        acked_packets.remove(base - 1)
                except socket.timeout:
                    # Timeout: retransmit packets from base to next_seq_num
                    for i in range(base, next_seq_num):
                        if i not in acked_packets:
                            try:
                                send_packet(sock, receiver, i, 0, 0, buffer[i - base])
                            except socket.error as e:
                                return False, f"Socket error: {e}"
                            except Exception as e:
                                return False, f"Unexpected error: {e}"
                except socket.error as e:
                    return False, f"Socket error: {e}"
                except Exception as e:
                    return False, f"Unexpected error: {e}"

                if not buffer[0]:
                    break

    elif receiver:
        with open(file, 'wb') as file:
            recv_buffer = {}
            expected_seq_num = 0

            while True:
                seq_num, _, _, data, _ = receive_packet(sock)
                if seq_num is not None:
                    recv_buffer[seq_num] = data

                    # Write consecutive packets to the file
                    while expected_seq_num in recv_buffer:
                        file.write(recv_buffer.pop(expected_seq_num))
                        expected_seq_num += 1

                # Send acknowledgment
                try:
                    if seq_num is not None:
                        send_packet(sock, sender, 0, seq_num, 0, b'')
                except socket.error as e:
                    return False, f"Socket error: {e}"
                except Exception as e:
                    return False, f"Unexpected error: {e}"

                if not data:
                    break

    return True, None


def server(port, file, reliability_method):
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind(('localhost', port))
        server_socket.settimeout(TIMEOUT)
    except socket.error as e:
        return False, f"Socket error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"

    client_address = None

    print("Server is listening...")
    while not client_address:
        try:
            _, _, _, _, client_address = receive_packet(server_socket)
        except socket.timeout:
            server_socket.close()
            return False, "Server timed out while waiting for a connection"
        except socket.error as e:
            server_socket.close()
            return False, f"Socket error: {e}"
        except Exception as e:
            server_socket.close()
            return False, f"Unexpected error: {e}"

    success, error = False, None
    try:
        if reliability_method == 'stop_and_wait':
            success, error = stop_and_wait(server_socket, client_address, file)
        elif reliability_method == 'gbn':
            success, error = go_back_n(server_socket, client_address, file, WINDOW_SIZE)
        elif reliability_method == 'sr':
            success, error = selective_repeat(server_socket, client_address, file, WINDOW_SIZE)
    except Exception as e:
        success, error = False, f"Unexpected error during file transfer: {e}"

    server_socket.close()

    if not success:
        return False, error
    return True, None


def client(server_addr, server_port, file, reliability_method):
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_socket.settimeout(TIMEOUT)
    except socket.error as e:
        return False, f"Socket error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"

    server_address = (server_addr, server_port)

    success, error = False, None
    try:
        if reliability_method == 'stop_and_wait':
            success, error = stop_and_wait(client_socket, server_address, server_address, file)
        elif reliability_method == 'gbn':
            success, error = go_back_n(client_socket, server_address, file, WINDOW_SIZE)
        elif reliability_method == 'sr':
            success, error = selective_repeat(client_socket, server_address, file, WINDOW_SIZE)
    except Exception as e:
        success, error = False, f"Unexpected error during file transfer: {e}"

    client_socket.close()

    if not success:
        return False, error
    return True, None


def main():
    try:
        args = argument_parser()
        args.file = os.path.abspath(os.path.join(os.getcwd(), args.file))

        if not args.server and not args.client:
            print("Error: either -s or -c flag must be provided.")
            args.print_usage()
            return

        if args.server:
            success, error = server(args.port, args.file, args.reliability)
            if not success:
                print(f"Server error: {error}", file=sys.stderr)
                sys.exit(1)
        elif args.client:
            success, error = client(args.IP, args.port, args.file, args.reliability)
            if not success:
                print(f"Client error: {error}", file=sys.stderr)
                sys.exit(1)

    except argparse.ArgumentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
