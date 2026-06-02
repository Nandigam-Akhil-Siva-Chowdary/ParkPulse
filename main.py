import RPi.GPIO as GPIO
import time
import threading
import json
from flask import Flask, render_template, jsonify
import signal
import sys


ENTRY_THRESHOLD = 20     
EXIT_THRESHOLD = 20       
OCCUPIED_THRESHOLD = 30   


GATE_OPEN_ANGLE = 90
GATE_CLOSED_ANGLE = 0


SLOT_ANGLES = [20, 40, 60, 80] 
NUM_SLOTS = 4

GATE_OPEN_TIME = 3       
SERVO_SETTLE_TIME = 0.5  
RADAR_SCAN_DELAY = 0.8    
ENTRY_COOLDOWN = 4        
ENTRY_TRIG = 17
ENTRY_ECHO = 27
EXIT_TRIG = 22
EXIT_ECHO = 23
RADAR_TRIG = 24
RADAR_ECHO = 25

ENTRY_SERVO_PIN = 18
EXIT_SERVO_PIN = 19
RADAR_SERVO_PIN = 21

slot_status = [False] * NUM_SLOTS  
entry_count = 0
total_cars_today = 0
entry_in_progress = False
exit_in_progress = False
last_entry_time = 0
last_exit_time = 0
lock = threading.Lock()

# Flask app
app = Flask(__name__, template_folder='web/templates', static_folder='web/static')

class UltrasonicSensor:
    def __init__(self, trig_pin, echo_pin):
        self.trig = trig_pin
        self.echo = echo_pin
        GPIO.setup(self.trig, GPIO.OUT)
        GPIO.setup(self.echo, GPIO.IN)
        GPIO.output(self.trig, False)
        time.sleep(0.1)
    
    def get_distance(self):
        """Measure distance in cm"""

        GPIO.output(self.trig, True)
        time.sleep(0.00001)
        GPIO.output(self.trig, False)

        pulse_start = time.time()
        pulse_end = time.time()
        timeout = 0.1  
        
        while GPIO.input(self.echo) == 0:
            pulse_start = time.time()
            if pulse_start - pulse_end > timeout:
                return -1
        
        while GPIO.input(self.echo) == 1:
            pulse_end = time.time()
            if pulse_end - pulse_start > timeout:
                return -1
        
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150 
        distance = round(distance, 2)
        return distance


class ServoMotor:
    def __init__(self, pin, frequency=50):
        self.pin = pin
        self.frequency = frequency
        GPIO.setup(self.pin, GPIO.OUT)
        self.pwm = GPIO.PWM(self.pin, frequency)
        self.pwm.start(0)
        time.sleep(0.1)
    
    def set_angle(self, angle):
        """Set servo angle (0-180 degrees)"""
        
        duty = 2.5 + (angle / 180.0) * 10.0
        self.pwm.ChangeDutyCycle(duty)
        time.sleep(0.1)  
        
    def cleanup(self):
        self.pwm.stop()


def radar_scan_thread():
    """Continuously rotates servo to check slot occupancy"""
    global slot_status
    radar_servo = ServoMotor(RADAR_SERVO_PIN)
    radar_sensor = UltrasonicSensor(RADAR_TRIG, RADAR_ECHO)
    
    try:
        while True:
            for i, angle in enumerate(SLOT_ANGLES):
               
                radar_servo.set_angle(angle)
                time.sleep(SERVO_SETTLE_TIME)
                
                
                distance = radar_sensor.get_distance()
                
                
                with lock:
                    if distance > 0 and distance < OCCUPIED_THRESHOLD:
                        slot_status[i] = True 
                    else:
                        slot_status[i] = False 
                
              
                time.sleep(RADAR_SCAN_DELAY)
                
    except Exception as e:
        print(f"Radar scan error: {e}")
    finally:
        radar_servo.cleanup()

def entry_monitor_thread():
    """Monitors entry ultrasonic and opens gate when car detected"""
    global entry_count, total_cars_today, entry_in_progress, last_entry_time, slot_status
    
    entry_sensor = UltrasonicSensor(ENTRY_TRIG, ENTRY_ECHO)
    entry_servo = ServoMotor(ENTRY_SERVO_PIN)
    
    try:
        while True:
            distance = entry_sensor.get_distance()
            
            with lock:
                free_slots = NUM_SLOTS - sum(slot_status)
                current_time = time.time()
                
                
                if (distance > 0 and distance < ENTRY_THRESHOLD and 
                    free_slots > 0 and 
                    not entry_in_progress and 
                    current_time - last_entry_time > ENTRY_COOLDOWN):
                    
                    entry_in_progress = True
                    
                    
                    print(f"🚗 Car detected at entry - Opening gate (Free slots: {free_slots})")
                    entry_servo.set_angle(GATE_OPEN_ANGLE)
                    time.sleep(GATE_OPEN_TIME)
                    
                    
                    entry_count += 1
                    total_cars_today += 1
                    print(f"📊 Total cars today: {total_cars_today}")
                    
                    
                    entry_servo.set_angle(GATE_CLOSED_ANGLE)
                    
                    
                    entry_in_progress = False
                    last_entry_time = time.time()
                    
            time.sleep(0.2) 
            
    except Exception as e:
        print(f"Entry monitor error: {e}")
    finally:
        entry_servo.cleanup()


def exit_monitor_thread():
    """Monitors exit ultrasonic and opens gate when car detected"""
    global exit_in_progress, last_exit_time
    
    exit_sensor = UltrasonicSensor(EXIT_TRIG, EXIT_ECHO)
    exit_servo = ServoMotor(EXIT_SERVO_PIN)
    
    try:
        while True:
            distance = exit_sensor.get_distance()
            
            current_time = time.time()
            if (distance > 0 and distance < EXIT_THRESHOLD and 
                not exit_in_progress and 
                current_time - last_exit_time > ENTRY_COOLDOWN):
                
                exit_in_progress = True
                
                
                print("🚗 Car detected at exit - Opening gate")
                exit_servo.set_angle(GATE_OPEN_ANGLE)
                time.sleep(GATE_OPEN_TIME)
                
                
                exit_servo.set_angle(GATE_CLOSED_ANGLE)
                
                
                exit_in_progress = False
                last_exit_time = time.time()
                
            time.sleep(0.2)
            
    except Exception as e:
        print(f"Exit monitor error: {e}")
    finally:
        exit_servo.cleanup()

@app.route('/')
def index():
    """Serve dashboard"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Return current parking status as JSON"""
    with lock:
        free_slots = NUM_SLOTS - sum(slot_status)
        status = {
            'slots': [{'id': i+1, 'occupied': slot_status[i]} for i in range(NUM_SLOTS)],
            'total_cars_today': total_cars_today,
            'free_slots': free_slots,
            'occupied_slots': sum(slot_status),
            'total_slots': NUM_SLOTS
        }
    return jsonify(status)

@app.route('/api/reset')
def reset_count():
    """Reset daily car count (optional)"""
    global total_cars_today
    with lock:
        total_cars_today = 0
    return jsonify({'message': 'Counter reset successfully'})

def cleanup(signum=None, frame=None):
    print("\n🛑 Shutting down ParkPulse...")
    GPIO.cleanup()
    sys.exit(0)

def main():

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    print("=" * 50)
    print("🚀 ParkPulse Smart Parking System Started")
    print("=" * 50)
    

    radar_thread = threading.Thread(target=radar_scan_thread, daemon=True)
    entry_thread = threading.Thread(target=entry_monitor_thread, daemon=True)
    exit_thread = threading.Thread(target=exit_monitor_thread, daemon=True)
    
    radar_thread.start()
    entry_thread.start()
    exit_thread.start()
    
    print("✅ Radar scanning active")
    print("✅ Entry gate monitoring active")
    print("✅ Exit gate monitoring active")
    print("🌐 Web dashboard available at http://raspberrypi:5000")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    main()