#!/usr/bin/python

# Raspberry Pi GPIO-controlled REST API

from flask import Flask, request
from flask_restx import Api, Resource, fields, reqparse
import RPi.GPIO as GPIO
from subprocess import Popen, PIPE
import requests
import serial
import os, sys, signal, time
from threading import Thread, Lock

app = Flask(__name__)
api = Api(app,
          version='1.1',
          title='RESTFUL Pi++',
          description='A RESTFUL API to control the GPIO pins of a Raspberry Pi for signal box simulation',
          doc='/docs')

ns = api.namespace('pins', description='Pin related operations')

GPIO_BOUNCE_TIME = 10    # millisecs

pin_model = api.model('pins', {
    'id': fields.Integer(readonly=True, description='The pin unique identifier'),
    'pin_num': fields.Integer(required=True, description='GPIO pin associated with this endpoint'),
    'color': fields.String(required=False, description='LED color (multiples allowed)'),
    'name': fields.String(required=False, description='function name (must be unique)'),
    'state': fields.String(required=False, description='LED on or off'),
    'direction': fields.String(required=True, description='in (for opto input) or out (for LED/relay)'),
    'rising_url': fields.String(required=False, description='URL to PUT on rising edge of input'),
    'falling_url': fields.String(required=False, description='URL to PUT on falling edge of input'),
    'rising_video': fields.String(required=False, description='video to play on rising edge of input'),
    'falling_video': fields.String(required=False, description='video to play on falling edge of input'),
    'rising_serial': fields.String(required=False, description='string to send on rising edge of input'),
    'falling_serial': fields.String(required=False, description='string to send on falling edge of input'),
})

# Duration of a bell pulse when you set the state to 'pulse'
pulse_period = 0.15
gap_period = 0.25


class PinUtil(object):
    def __init__(self):
        self.counter = 0
        self.pins = []
        self._mutex = Lock()
        self.debug = 1
        self.pull_up_down = GPIO.PUD_UP
        
        # The currently playing video filename
        self._active_vid = None

        # The process of the active video player
        self._p = None

        # mser = serial.Serial('/dev/rfcomm0', 9600)  # open serial port
        # print(ser.name)         # check which port was really used
        #ser.write(b'hello')     # write a string
        #ser.close()             # close port

    def set_pull_up_down(self, pull_up_down):
        self.pull_up_down = pull_up_down
        print(f"Pull Up or Down = ${pull_up_down}")


    def get(self, id):
        for pin in self.pins:
            if pin['id'] == id:
                return pin
        api.abort(404, f"pin {id} doesn't exist.")


    def create(self, data):
        pin = data
        pin['id'] = self.counter = self.counter + 1
        self.pins.append(pin)
        self.last_pinchange_time = time.clock_gettime(1)

        if pin['direction'] == 'in':
            GPIO.setup(pin['pin_num'], GPIO.IN, pull_up_down=self.pull_up_down)
            pin['state'] = 'on' if GPIO.input(pin['pin_num']) else 'off'

            if 'rising_video' in pin:
                filename = pin['rising_video']
                if not os.path.exists(filename):
                    if os.path.exists(f"/home/pi/Videos/{filename}"):
                        pin['rising_video'] = f"/home/pi/Videos/{filename}"
                        print(f"rising_video is /home/pi/Videos/{filename}")
                    else:
                        print(f"Can't find {filename} or /home/pi/Videos/{filename}")

            if 'falling_video' in pin:
                filename = pin['falling_video']
                if not os.path.exists(filename):
                    if os.path.exists(f"/home/pi/Videos/{filename}"):
                        pin['falling_video'] = f"/home/pi/Videos/{filename}"
                        print(f"falling_video is /home/pi/Videos/{filename}")
                    else:
                        print(f"Can't find {filename} or /home/pi/Videos/{filename}")

            if 'rising_url' in pin:
                if 'falling_url' in pin:
                    GPIO.add_event_detect(pin['pin_num'], GPIO.BOTH, callback=self.pin_change,
                                  bouncetime=GPIO_BOUNCE_TIME)
                else:
                    GPIO.add_event_detect(pin['pin_num'], GPIO.RISING, callback=self.pin_change,
                                  bouncetime=GPIO_BOUNCE_TIME)
            else:
                if 'falling_url' in pin:
                    GPIO.add_event_detect(pin['pin_num'], GPIO.FALLING, callback=self.pin_change,
                                  bouncetime=GPIO_BOUNCE_TIME)
            return pin
        else:
            # It is an output pin
            GPIO.setup(pin['pin_num'], GPIO.OUT)

            if pin['state'] == 'off':
                GPIO.output(pin['pin_num'], GPIO.LOW)
            elif pin['state'] == 'on':
                GPIO.output(pin['pin_num'], GPIO.HIGH)

        return pin


    def update(self, id, data):
        print("Update", id, "data", data)
        if data is None:
            api.abort(400, "Must supply data")
        pin = self.get(id)
        pin.update(data)  # this is the dict_object update method
        
        if pin['direction'] == 'in':
            pin['state'] = 'on' if GPIO.input(pin['pin_num']) else 'off'
            return pin

        if pin['state'] == 'off':
            GPIO.output(pin['pin_num'], GPIO.LOW)
        elif pin['state'] == 'on':
            GPIO.output(pin['pin_num'], GPIO.HIGH)
        elif pin['state'] == 'pulse':
            GPIO.output(pin['pin_num'], GPIO.HIGH)
            time.sleep(pulse_period)
            GPIO.output(pin['pin_num'], GPIO.LOW)
            pin['state'] = 'off'
            time.sleep(gap_period)
        elif pin['state'] == 'pulse01':
            GPIO.output(pin['pin_num'], GPIO.LOW)
            time.sleep(pulse_period)
            GPIO.output(pin['pin_num'], GPIO.HIGH)
            pin['state'] = 'on'
            time.sleep(gap_period)
        return pin


    def pin_change(self, pin_num):
        """
        Send any appropriate request for the changed pin.
        
        """
        # Use a mutex lock to avoid race condition when
        # multiple inputs change in quick succession
        with self._mutex:
            # If we haven't been here recently, this could be the first transition of a cluster caused by noise
            if self.last_pinchange_time < time.clock_gettime(1) - 0.1:
                time.sleep(0.1)
                self.last_pinchange_time = time.clock_gettime(1)
            new_state = 'on' if GPIO.input(pin_num) else 'off'
            # print (f"pin {pin_num} state {new_state}")
            # Look for a 'pin' on this pin_num
            for pin in pin_util.pins:
                # print (f"Comparing {pin_num} to {pin['pin_num']} and {pin['state']} to {new_state}")
                # If found it and it has changed
                if pin['pin_num'] == pin_num:
                    # print ("Found pin", pin_num, pin['name'])
                    if pin['state'] != new_state:
                        print ("Input changed state from", pin['state'], "to", new_state)
                        pin['state'] = new_state
                        if new_state == 'on':
                            if 'rising_url' in pin:
                                print('Calling rising_url', pin['rising_url'], new_state)
                                requests.get(pin['rising_url'])
                            if 'rising_video' in pin:
                                print('Calling rising_video', pin['rising_video'], new_state)
                                self.switch_vid(pin['rising_video'])
                            if 'rising_serial' in pin:
                                print('Calling rising_serial', pin['rising_serial'], new_state)
                                ser.write(pin['rising_serial'])
                        if new_state == 'off':
                            if 'falling_url' in pin:
                                print('Calling falling_url', pin['falling_url'], new_state)
                                requests.get(pin['falling_url'])
                            if 'falling_video' in pin:
                                print('Calling falling_video', pin['falling_video'], new_state)
                                self.switch_vid(pin['falling_video'])
                            if 'falling_serial' in pin:
                                print('Calling falling_serial', pin['falling_serial'], new_state)
                                ser.write(pin['falling_serial'])
                    return

# Following based on vidlooper.py
    def switch_vid(self, filename):
        """ Switch to the video corresponding to the shorted pin """

        print(f"switch_vid {filename}")

        if filename != self._active_vid or self.restart_on_press:
            # Kill any previous video player process
            self._kill_process()
            # Start a new video player process, capture STDOUT to keep the
            # screen clear. Set a session ID (os.setsid) to allow us to kill
            cmd = ['cvlc', '--fullscreen', f"file://{filename}"]
            print(cmd)

            self._p = Popen(cmd, stdout=None if self.debug else PIPE, preexec_fn=os.setsid)
            self._active_vid = filename

    def _kill_process(self):
        """ Kill a video player process. SIGINT seems to work best. """
        if self._p is not None:
            os.killpg(os.getpgid(self._p.pid), signal.SIGINT)
            print(f"Killing process {self._p.pid}")
            self._p = None
        else:
            print("No video running")
# end vidlooper.py bits

@ns.route('/')  # keep in mind this our ns-namespace (pins/)
class PinList(Resource):
    """Shows a list of all pins, and lets you POST to add new pins"""

    @ns.marshal_list_with(pin_model)
    def get(self):
        """List all pins"""
        return pin_util.pins

    @ns.expect(pin_model)
    @ns.marshal_with(pin_model, code=201)
    def post(self):
        """Create a new pin"""
        return pin_util.create(api.payload)


@ns.route('/<int:id>')
@ns.response(404, 'pin not found')
@ns.param('id', 'The pin identifier')
@ns.param('state', 'Pin state on, off, or pulse')
class Pin(Resource):
    """Show a single pin item and lets you update it"""

    @ns.marshal_with(pin_model)
    def get(self, id):
        """Fetch a pin given its resource identifier. Optionally set the state"""
        parser = reqparse.RequestParser()
        parser.add_argument('state', choices=('on', 'off', 'pulse', 'pulse01') )
        args = parser.parse_args()
        print('Get pin ID', id, args)
        if args['state']:
            return pin_util.update(id, args)
        return pin_util.get(id)

    # @ns.expect(pin_model, validate=True)
    @ns.expect(pin_model)
    @ns.marshal_with(pin_model)
    def put(self, id):
        print('Put pin ID', id, "payload", api.payload)
        """Update a pin given its identifier (Not working, as api.payload returns None)"""
        return pin_util.update(id, api.payload)

@ns.route('/name/<string:name>')
@ns.response(404, 'pin not found')
@ns.param('name', 'The pin function name')
class PinName(Resource):
    """Show a single pin item and lets you update it"""

    @ns.marshal_with(pin_model)
    def get(self, name):
        
        """Fetch a pin given its function name. Optionally set the state"""
        parser = reqparse.RequestParser()
        parser.add_argument('state', choices=('on', 'off', 'pulse', 'pulse01') )
        args = parser.parse_args()
        print('Get pin with name', name, args)

        for pin in pin_util.pins:
            if pin['name'] == name:
                if args['state']:
                    return pin_util.update(pin['id'], args)
                return pin_util.get(pin['id'])
        api.abort(404, f"pin {name} doesn't exist.")
    
    # @ns.expect(pin_model, validate=True)
    @ns.expect(pin_model)
    @ns.marshal_with(pin_model)
    def put(self, name):
        #record = json.loads(request.data)
        print('Putting pin with name', name, "payload", api.payload, request.data)
        """Update a pin given its function name"""
        for pin in pin_util.pins:
            # print('Checking', pin['name'])
            if pin['name'] == name:
                print('Updating', pin['name'], "payload", api.payload)
                return pin_util.update(pin['id'], api.payload)
        api.abort(404, f"pin {name} doesn't exist.")


if __name__ == '__main__':
    GPIO.setmode(GPIO.BCM)
    host = 'http://localhost:5000/pins/name'
    mode = "levers"

    pin_util = PinUtil()

    if len(sys.argv) > 1:
        mode = sys.argv[1]

    if len(sys.argv) > 2:
        host = sys.argv[2]

    print (f"mode is {mode}, host is {host}")

    if mode == 'vidlooper':
        pin_util.set_pull_up_down(GPIO.PUD_UP)

        pin_util.create({'pin_num': 21, 'name': 'led1', 'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 20, 'name': 'led2', 'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 16, 'name': 'led3', 'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 12, 'name': 'led4', 'state': 'off', 'direction': 'out'})
        
        pin_util.create({'pin_num': 26, 'name': 'button1',  'direction': 'in', 'falling_url': f'{host}/led1?state=off', 'rising_url': f'{host}/led1?state=on'})
        pin_util.create({'pin_num': 19, 'name': 'button2',  'direction': 'in', 'falling_url': f'{host}/led2?state=off', 'rising_url': f'{host}/led2?state=on'})
        pin_util.create({'pin_num': 13, 'name': 'button3',  'direction': 'in', 'rising_url': f'{host}/led3?state=pulse'})
        pin_util.create({'pin_num':  6, 'name': 'button4',  'direction': 'in', 'falling_url': f'{host}/led4?state=off', 'rising_url': f'{host}/led4?state=on'})

    elif mode == 'block':
        pin_util.set_pull_up_down(GPIO.PUD_UP)

        pin_util.create({'pin_num': 21, 'name': 'appr_bell',  'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 20, 'name': 'tc4601',     'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 16, 'name': 'lh-bj-bell', 'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 12, 'name': 'lh-bj-lc',   'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 25, 'name': 'lh-bj-tol',  'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 24, 'name': 'lh-th-lc',   'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 23, 'name': 'lh-th-tol',  'state': 'off', 'direction': 'out'})
        pin_util.create({'pin_num': 18, 'name': 'lh-th-bell', 'state': 'off', 'direction': 'out'})

        pin_util.create({'pin_num': 17, 'name': 'th-lh-tap',  'direction': 'in', 'falling_url': f'{host}/th-lh-tap/on'})
        pin_util.create({'pin_num': 27, 'name': 'th-lh-tol',  'direction': 'in', 'falling_url': f'{host}/th-lh-tol/off', 'rising_url': f'{host}/th-lh-tol/on'})
        pin_util.create({'pin_num': 22, 'name': 'th-lh-lc',   'direction': 'in', 'falling_url': f'{host}/th-lh-lc/off',  'rising_url': f'{host}/th-lh-lc/on'})
        pin_util.create({'pin_num':  5, 'name': 'bj-lh-tol',  'direction': 'in', 'falling_url': f'{host}/bj-lh-tol/off', 'rising_url': f'{host}/bj-lh-tol/on'})
        pin_util.create({'pin_num':  6, 'name': 'bj-lh-lc',   'direction': 'in', 'falling_url': f'{host}/bj-lh-lc/off',  'rising_url': f'{host}/bj-lh-lc/on'})
        pin_util.create({'pin_num': 13, 'name': 'bj-lh-tap',  'direction': 'in', 'falling_url': f'{host}/bj-lh-tap/on'})

    elif mode ==  'levers':
        pin_util.set_pull_up_down(GPIO.PUD_DOWN)

        pin_util.create({'pin_num': 18, 'name': 'lever-1',  'direction': 'in', 'falling_url': f'{host}/lever/1/N', 'rising_url': f'{host}/lever/1/R'})
        pin_util.create({'pin_num': 23, 'name': 'lever-2',  'direction': 'in', 'falling_url': f'{host}/lever/2/N', 'rising_url': f'{host}/lever/2/R'})
        pin_util.create({'pin_num': 24, 'name': 'lever-3',  'direction': 'in', 'falling_url': f'{host}/lever/3/N', 'rising_url': f'{host}/lever/3/R'})
        pin_util.create({'pin_num': 25, 'name': 'lever-4',  'direction': 'in', 'falling_url': f'{host}/lever/4/N', 'rising_url': f'{host}/lever/4/R', 'falling-serial': '4N', 'rising-serial': '4R'})
        pin_util.create({'pin_num': 12, 'name': 'lever-5',  'direction': 'in', 'falling_url': f'{host}/lever/5/N', 'rising_url': f'{host}/lever/5/R'})
        pin_util.create({'pin_num': 16, 'name': 'lever-6',  'direction': 'in', 'falling_url': f'{host}/lever/6/N', 'rising_url': f'{host}/lever/6/R'})
        pin_util.create({'pin_num': 20, 'name': 'lever-7',  'direction': 'in', 'falling_url': f'{host}/lever/7/N', 'rising_url': f'{host}/lever/7/R'})
        # pin_util.create({'pin_num': 21, 'name': 'spare',   'direction': 'in', 'falling_url': f'{host}/lever/x/N', 'rising_url': f'{host}/lever/x/R'})

        pin_util.create({'pin_num': 17, 'name': 'lever-8',  'direction': 'in', 'falling_url': f'{host}/lever/8/N', 'rising_url': f'{host}/lever/8/R'})
        pin_util.create({'pin_num': 27, 'name': 'lever-9',  'direction': 'in', 'falling_url': f'{host}/lever/9/N', 'rising_url': f'{host}/lever/9/R'})
        pin_util.create({'pin_num': 22, 'name': 'lever-10',  'direction': 'in', 'falling_url': f'{host}/lever/10/N', 'rising_url': f'{host}/lever/10/R'})
        pin_util.create({'pin_num':  5, 'name': 'lever-11',  'direction': 'in', 'falling_url': f'{host}/lever/11/N', 'rising_url': f'{host}/lever/11/R'})
        pin_util.create({'pin_num':  6, 'name': 'lever-12',  'direction': 'in', 'falling_url': f'{host}/lever/12/N', 'rising_url': f'{host}/lever/12/R'})
        pin_util.create({'pin_num': 13, 'name': 'lever-13',  'direction': 'in', 'falling_url': f'{host}/lever/13/N', 'rising_url': f'{host}/lever/13/R', 'falling-serial': '13N', 'rising-serial': '13R'})
        pin_util.create({'pin_num': 19, 'name': 'lever-14',  'direction': 'in', 'falling_url': f'{host}/lever/14/N', 'rising_url': f'{host}/lever/14/R', 'falling_video': '1-Gates-opening.mp4', 'rising_video': '2-Gates-closing.mp4'})
        # pin_util.create({'pin_num': 26, 'name': 'spare2',   'direction': 'in', 'falling_url': f'{host}/lever/y/N', 'rising_url': f'{host}/lever/y/R'})

    app.run(debug=False, host='0.0.0.0')
