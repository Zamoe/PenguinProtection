import serial
import time

class UART:
    def __init__(self, port="/dev/serial0", baudrate=115200, timeout=1):
        
        self.ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        if not self.ser.is_open:
            self.ser.open()
#get and recieve uart
    def send_and_wait_ack(self, message, ack="ACK", timeout=2, retries=3):
    #try and send uart for amount of retries otherwise fail
        for attempt in range(1, retries + 1):
            self.send(message)
            start_time = time.time()
            while time.time() - start_time < timeout:
                response = self.receive()
                if response == ack:
                    return True
                time.sleep(0.1)
            print(f"⚠️ Attempt {attempt} failed: No ack received, retrying...")
        return False


    def close(self):
        Close UART port.
        
        if self.ser.is_open:
            self.ser.close()


# For testing 
if __name__ == "__main__":
    uart = UART()
    print("Sending test message and waiting for ACK...")
    if uart.send_and_wait_ack("Hello ESP32"):
        print("ACK received!")
    else:
        print("No ACK received.")
    uart.close()
