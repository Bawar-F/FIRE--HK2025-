import pigpio
import time

# -----------------------------
# Configuration
# -----------------------------
TX = 18  # GPIO pin for TX (output)
RX = 27  # GPIO pin for RX (input)
BAUD = 9600  # Use the working baud rate

# -----------------------------
# Initialize pigpio
# -----------------------------
pi = pigpio.pi()
if not pi.connected:
    print("Failed to connect to pigpio daemon")
    exit()

pi.set_mode(TX, pigpio.OUTPUT)
pi.set_mode(RX, pigpio.INPUT)

# Initialize RX for software serial
pi.bb_serial_read_open(RX, BAUD)

# -----------------------------
# Bit-banged TX function (already working)
# -----------------------------
def bb_serial_send_wave(pi, tx_pin, text, baud=9600):
    data_bytes = text.encode('utf-8')
    bit_time_us = int(1e6 / baud)  # microseconds per bit

    for byte in data_bytes:
        wf = []

        # Start bit (LOW)
        wf.append(pigpio.pulse(0, 1 << tx_pin, bit_time_us))

        # Data bits LSB first
        for i in range(8):
            if (byte >> i) & 1:
                wf.append(pigpio.pulse(1 << tx_pin, 0, bit_time_us))  # HIGH
            else:
                wf.append(pigpio.pulse(0, 1 << tx_pin, bit_time_us))  # LOW

        # Stop bit (HIGH)
        wf.append(pigpio.pulse(1 << tx_pin, 0, bit_time_us))

        # Send waveform
        pi.wave_add_generic(wf)
        wid = pi.wave_create()
        if wid >= 0:
            pi.wave_send_once(wid)
            while pi.wave_tx_busy():
                time.sleep(0.001)
            pi.wave_delete(wid)

# -----------------------------
# Menu loop
# -----------------------------
def menu():
    while True:
        print("\n=== HM-10 Menu ===")
        print("1: Send a message")
        print("2: Listen for a message")
        print("q: Quit")
        choice = input("Enter choice: ").strip()

        if choice == "1":
            for x in [10,20,30,40,10,20,100,150,-23,-53]:
                BAUD = 19600
                #msg = input("Enter message to send: ")
                bb_serial_send_wave(pi, TX, str(x) + "\r\n", BAUD)
                time.sleep(0.1)
            print("Message sent!")
        elif choice == "2":
            BAUD = 9600
            print("Listening for data... (Ctrl+C to stop)")
            try:
                while True:
                    count, data = pi.bb_serial_read(RX)
                    if count > 0:
                        try:
                            text = data.decode("utf-8")
                            print("Received:", text)
                        except UnicodeDecodeError:
                            print("Recieved raw bytes:",data)
                        break
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("Stopped listening.")
        elif choice.lower() == "q":
            print("Exiting menu.")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or q.")

# -----------------------------
# Run the menu
# -----------------------------
try:
    menu()
finally:
    # Cleanup
    pi.bb_serial_read_close(RX)
    pi.stop()

