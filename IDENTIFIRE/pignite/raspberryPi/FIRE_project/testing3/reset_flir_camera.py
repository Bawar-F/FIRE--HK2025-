import RPi.GPIO as GPIO
import time
import subprocess


RESET_PIN = 26  # <-- GPIO26

GPIO.setmode(GPIO.BCM)

# idle: float as input so breakout pull-up holds HIGH
GPIO.setup(RESET_PIN, GPIO.IN)

def reset_camera():
    # assert reset (active LOW)
    GPIO.setup(RESET_PIN, GPIO.OUT)
    GPIO.output(RESET_PIN, GPIO.LOW)
    time.sleep(1.5)  # 50 ms (10–100 ms typical)

    # release reset
    GPIO.setup(RESET_PIN, GPIO.IN)

    time.sleep(1.2)
    
    subprocess.run(["sudo", "rpi_vsync_app"])

try:
    print("Resetting camera...")
    reset_camera()
    print("Done.")

finally:
    GPIO.cleanup()

