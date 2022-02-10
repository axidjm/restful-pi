#!/usr/bin/python

# Raspberry Pi GPIO-controlled REST API

from flask import Flask
from flask_restx import Api, Resource, fields
import RPi.GPIO as GPIO
import requests
import time

app = Flask(__name__)
api = Api(app,
          version='1.1',
          title='RESTFUL Pi++',
          description='A RESTFUL API to control the GPIO pins of a Raspberry Pi',
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
})

# Duration of a bell pulse when you set the state to 'pulse'
pulse_period = 0.2

class PinUtil(object):
    def __init__(self):
        self.counter = 0
        self.pins = []


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
            GPIO.setup(pin['pin_num'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
            pin['state'] = 'on' if GPIO.input(pin['pin_num']) else 'off'

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

        return pin


    def pin_change(self, pin_num):
            """ Send any appropriate request for the changed pin """
            # Use a mutex lock to avoid race condition when
            # multiple inputs change in quick succession
            #with self._mutex:
            # If we haven't been here recently, this could be the first transition of a cluster caused by noise
            if self.last_pinchange_time < time.clock_gettime(1) - 0.1:
                time.sleep(0.1)
                self.last_pinchange_time = time.clock_gettime(1)
            new_state = 'on' if GPIO.input(pin_num) else 'off'
            print (f"pin {pin_num} state {new_state}")
            # Look for a 'pin' on this pin_num
            for pin in pin_util.pins:
                # print (f"Comparing {pin_num} to {pin['pin_num']} and {pin['state']} to {new_state}")
                # If found it and it has changed
                if pin['pin_num'] == pin_num:
                    print ("Found pin", pin_num)
                    if pin['state'] != new_state:
                        print ("Pin changed state from ", pin['state'], " to ", new_state)
                        pin['state'] = new_state
                        if new_state == 'on' and 'rising_url' in pin:
                            print(pin['rising_url'], new_state)
                            requests.put(pin['rising_url'], json={"state": new_state})
                        if new_state == 'off' and 'falling_url' in pin:
                            print(pin['falling_url'], new_state)
                            requests.put(pin['falling_url'], json={"state": new_state})
                    return


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
class Pin(Resource):
    """Show a single pin item and lets you update it"""

    @ns.marshal_with(pin_model)
    def get(self, id):
        """Fetch a pin given its resource identifier"""
        return pin_util.get(id)

    # @ns.expect(pin_model, validate=True)
    @ns.expect(pin_model)
    @ns.marshal_with(pin_model)
    def put(self, id):
        """Update a pin given its identifier"""
        return pin_util.update(id, api.payload)

@ns.route('/name/<string:name>')
@ns.response(404, 'pin not found')
@ns.param('name', 'The pin function name')
class PinName(Resource):
    """Show a single pin item and lets you update it"""

    @ns.marshal_with(pin_model)
    def get(self, name):
        """Fetch a pin given its function name"""
        for pin in pin_util.pins:
            if pin['name'] == name:
                return pin_util.get(pin['id'])

    # @ns.expect(pin_model, validate=True)
    @ns.expect(pin_model)
    @ns.marshal_with(pin_model)
    def put(self, name):
        """Update a pin given its function name"""
        for pin in pin_util.pins:
            if pin['name'] == name:
                return pin_util.update(pin['id'], api.payload)

GPIO.setmode(GPIO.BCM)

pin_util = PinUtil()
pin_util.create({'pin_num': 21, 'name': 'appr_bell',  'state': 'off', 'direction': 'out'})
pin_util.create({'pin_num': 20, 'name': 'tc4601',     'state': 'off', 'direction': 'out'})
pin_util.create({'pin_num': 16, 'name': 'lh-bj-bell', 'state': 'off', 'direction': 'out'})
pin_util.create({'pin_num': 12, 'name': 'lh-bj-lc',   'state': 'off', 'direction': 'out'})
pin_util.create({'pin_num': 25, 'name': 'lh-bj-tol',  'state': 'off', 'direction': 'out'})
pin_util.create({'pin_num': 24, 'name': 'lh-th-lc',   'state': 'off', 'direction': 'out'})
pin_util.create({'pin_num': 23, 'name': 'lh-th-tol',  'state': 'off', 'direction': 'out'})
pin_util.create({'pin_num': 18, 'name': 'lh-th-bell', 'state': 'off', 'direction': 'out'})

host = 'http://192.168.1.100/apipath'
pin_util.create({'pin_num': 17, 'name': 'th-lh-tap',  'direction': 'in', 'falling_url': f'{host}/th-lh-tap/on'})
pin_util.create({'pin_num':  6, 'name': 'bj-lh-lc',   'direction': 'in', 'falling_url': f'{host}/bj-lh-lc/off',  'rising_url': f'{host}/bj-lh-lc/on'})
pin_util.create({'pin_num':  5, 'name': 'bj-lh-tol',  'direction': 'in', 'falling_url': f'{host}/bj-lh-tol/off', 'rising_url': f'{host}/bj-lh-tol/on'})
pin_util.create({'pin_num': 22, 'name': 'th-lh-lc',   'direction': 'in', 'falling_url': f'{host}/th-lh-lc/off',  'rising_url': f'{host}/th-lh-lc/on'})
pin_util.create({'pin_num': 27, 'name': 'th-lh-tol',  'direction': 'in', 'falling_url': f'{host}/th-lh-tol/off', 'rising_url': f'{host}/th-lh-tol/on'})


if __name__ == '__main__':
    app.run(debug=True)
