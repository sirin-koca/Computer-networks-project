# DATA2410 - PORTFOLIO2:

# Import required libraries
import argparse
import socket
import struct
import time

# DRTP header format
header_format = 'I I H H'

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
    parser.add_argument('--host', type=str, help='host to connect to (default: localhost)', default='localhost')
    parser.add_argument('-p', '--port', type=int, help='port to connect to or bind to (default: 5000)', default=5000)
    parser.add_argument('-f', '--file', required=True, help='The path to the file to send or receive')
    parser.add_argument('-b', '--buffer_size', type=int, default=2048, help='Buffer size')
    parser.add_argument('-t', '--timeout', type=int, default=5, help='Timeout in seconds')
    parser.add_argument('-r', '--reliability', choices=['stop_and_wait', 'gbn', 'sr'], required=True,
                        help='Reliability method: stop_and_wait, gbn, or sr')
    parser.add_argument('--test', type=str, choices=['skipack', 'loss'], help='Test case: skipack or loss')
    return parser.parse_args()


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
    header = create_header(seq_num, ack_num, flags, len(data))
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


def establish_connection(sock, addr):
    syn_flag = 1 << 3
    send_packet(sock, addr, 0, 0, syn_flag, b'')
    seq_num, ack_num, flags, _, _ = receive_packet(sock)
    if parse_flags(flags)[0]:  # Check if SYN flag is set in the response
        return True
    else:
        return False


def teardown_connection(sock, addr):
    fin_flag = 1 << 1
    send_packet(sock, addr, 0, 0, fin_flag, b'')
    seq_num, ack_num, flags, _, _ = receive_packet(sock)
    if parse_flags(flags)[2]:  # Check if FIN flag is set in the response
        return True
    else:
        return False


# Reliable methods using 'socket' module
def stop_and_wait(sock, sender, receiver, file):
    if sender:  # If the application is running as the sender
        establish_connection(sock, receiver)
        with open(file, 'rb') as file:
            seq_num = 0
            while True:
                data = file.read(DATA_SIZE)
                if not data:
                    break

                # Send the packet and wait for acknowledgment
                while True:
                    send_packet(sock, receiver, seq_num, 0, 0, data)
                    _, ack_num, _, _, _ = receive_packet(sock)
                    if ack_num == seq_num:
                        break

                # Toggle the sequence number
                seq_num = 1 - seq_num

    elif receiver:  # If the application is running as the receiver
        teardown_connection(sock, sender)
        with open(file, 'wb') as file:
            expected_seq_num = 0
            while True:
                seq_num, _, _, data, _ = receive_packet(sock)
                if seq_num == expected_seq_num:
                    file.write(data)

                    # Toggle the expected sequence number
                    expected_seq_num = 1 - expected_seq_num

                # Send acknowledgment
                send_packet(sock, sender, 0, seq_num, 0, b'')


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
                        send_packet(sock, receiver, next_seq_num, 0, 0, data)
                        next_seq_num += 1

                # Wait for acknowledgments
                _, ack_num, _, _, _ = receive_packet(sock)
                base = ack_num + 1

                if not buffer[0]:
                    break

                # Remove acknowledged packets from the buffer
                buffer.pop(0)

    elif receiver:
        with open(file, 'wb') as file:
            expected_seq_num = 0

            while True:
                seq_num, _, _, data, _ = receive_packet(sock)
                if seq_num == expected_seq_num:
                    file.write(data)
                    expected_seq_num += 1

                # Send acknowledgment
                send_packet(sock, sender, 0, seq_num, 0, b'')


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
                        send_packet(sock, receiver, next_seq_num, 0, 0, data)
                        next_seq_num += 1

                # Wait for acknowledgments
                _, ack_num, _, _, _ = receive_packet(sock)
                if ack_num is not None:
                    acked_packets.add(ack_num)

                # Slide the window
                while base in acked_packets:
                    buffer.pop(0)
                    base += 1
                    acked_packets.remove(base - 1)

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
                if seq_num is not None:
                    send_packet(sock, sender, 0, seq_num, 0, b'')


def server(port, file, reliability_method):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind(('localhost', port))
    server_socket.settimeout(TIMEOUT)
    client_address = None

    while not client_address:
        _, _, _, _, client_address = receive_packet(server_socket)

    if reliability_method == 'stop_and_wait':
        stop_and_wait(server_socket, client_address, file)
    elif reliability_method == 'gbn':
        go_back_n(server_socket, client_address, file, WINDOW_SIZE)
    elif reliability_method == 'sr':
        selective_repeat(server_socket, client_address, file, WINDOW_SIZE)

    server_socket.close()


def client(server_addr, server_port, file, reliability_method):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT)
    server_address = (server_addr, server_port)

    if reliability_method == 'stop_and_wait':
        stop_and_wait(client_socket, server_address, server_address, file)
    elif reliability_method == 'gbn':
        go_back_n(client_socket, server_address, file, WINDOW_SIZE)
    elif reliability_method == 'sr':
        selective_repeat(client_socket, server_address, file, WINDOW_SIZE)

    client_socket.close()


def main():
    import os

    args = argument_parser()
    args.file = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), args.file))

    if args.server:
        server(args.port, args.file, args.reliability)
    elif args.client:
        client(args.host, args.port, args.file, args.reliability)


if __name__ == '__main__':
    main()
