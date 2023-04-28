# DATA2410-Portfolio2

# UDP File Transfer System with Reliability Layer

This project is a file transfer system implemented in UDP with a reliability layer. The system uses three reliability methods: stop-and-wait, Go-Back-N (GBN), and Selective Repeat (SR). This README file explains how to use the system and its different options.

## Prerequisites
* Python 3.6 or later.
* Some basic knowledge of the command line.

## Usage
Command-line arguments: The system takes the following command-line arguments:

* -c or --client: Starts the system as a client.
* -s or --server: Starts the system as a server.
* --host: Specifies the host to connect to (default: localhost).
* -p or --port: Specifies the port to connect to or bind to (default: 5000).
* -f or --file: Specifies the path to the file to send or receive (required).
* -b or --buffer_size: Specifies the buffer size (default: 2048).
* -t or --timeout: Specifies the timeout in seconds (default: 5).
* -r or --reliability: Specifies the reliability method: stop_and_wait, gbn, or sr (required).
* --test: Specifies the test case: skipack or loss.

## Starting the Server
To start the system as a server, run the following command:

`python application.py -s -p [port] -f [filename] -r [reliability method]`
For example, to start the server on port 5000 with the file "example.txt" using the GBN reliability method, run the following command:

`python application.py -s -p 5000 -f example.txt -r gbn`

## Starting the Client
To start the system as a client, run the following command:

`python application.py -c --host [host] -p [port] -f [filename] -r [reliability method]`
For example, to send the file "example.txt" to a server running on localhost with the GBN reliability method, run the following command:

`python application.py -c --host localhost -p 5000 -f example.txt -r gbn`

## Test Cases
To test the system with a specific test case, use the --test option. The system currently supports two test cases: skipack and loss.

1. skipack: Skips every other packet.
1. loss: Drops every other packet.

To use a test case, add the --test option followed by the name of the test case. For example, to use the "skipack" test case, run the following command:

`python application.py -c --host localhost -p 5000 -f example.txt -r gbn --test skipack`

## Reliability Methods

### Stop-and-Wait
The stop-and-wait method sends one packet at a time and waits for an acknowledgment before sending the next packet. This method is the simplest and easiest to implement but can be inefficient because it requires the sender to wait for an acknowledgment before sending the next packet.

To use the stop-and-wait method, use the -r or --reliability option followed by "stop_and_wait". For example:

`python application.py -s -p 5000 -f example.txt -r stop_and_wait`

### Go-Back-N
The Go-Back-N (GBN) method sends multiple packets without waiting for acknowledgments. The receiver acknowledges every Nth packet, where N is the window size. If a packet is lost or corrupted, the receiver discards all subsequent packets until the missing packet is received. This method can be more efficient than stop-and-wait but can also lead to increased network congestion.

To use the GBN method, use the -r or --reliability option followed by "gbn". For example:

`python application.py -s -p 5000 -f example.txt -r gbn`

### Selective Repeat
The Selective Repeat (SR) method is similar to GBN but allows the receiver to selectively acknowledge individual packets. This can be more efficient than GBN in situations where there are only a few lost or corrupted packets. However, implementing SR can be more complex than implementing GBN.

To use the SR method, use the -r or --reliability option followed by "sr". For example:

`python application.py -s -p 5000 -f example.txt -r sr`

---

DATA2410 Portfolio2 | Group Project | OsloMet 2023 | [sirin-koca](https://github.com/sirin-koca)
