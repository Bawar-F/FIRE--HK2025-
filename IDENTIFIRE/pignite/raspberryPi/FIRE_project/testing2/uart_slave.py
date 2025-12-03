import serial, time, subprocess

ser = serial.Serial('/dev/serial0', 9600, timeout=1)
time.sleep(2)

while True:
	if ser.in_waiting > 0:
		cmd = ser.readline().decode("utf-8", errors="replace").strip()
		print(f"recieved {cmd}")
		if cmd == "CAPTURE":
			try:
				data = "testing some data"
				ser.write((data + "\n").encode())
			except Exception as e:
				ser.write((f"error {e}\n").encode())


