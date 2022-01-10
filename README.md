# RESTful Pi
This is a Flask app written in Python3. This app is a REST API backend to control the GPIO pins of a Raspberry Pi by making HTTP requests to the `/pins` and `/pins/<id>` endpoints. This project uses a breadboard outfitted with LEDs connected to the Raspberyy Pi's GPIO pins to demonstrate the correct function of the API calls. This app could easily be extended to trigger and process more complex events to control the pins of a Pi beyond lighting up a couple LEDs.

It builds on the original version by avcourt by allowing you to define URLs that will be posted to when a pin changes, and adding a PULSE option.

A step-by-step tutorial I wrote to get started with this project can be found [here](https://avcourt.github.io/tiny-cluster/2019/09/18/pi_led.html).

A video series I published on YouTube going over this project can be found [here](https://www.youtube.com/playlist?list=PLLIDdNg0t5ceg3mI3vn0YJocJ4ndMtM98).

## HTTP Methods
These requests use the standard HTTP requests `GET`, `POST`, and `PUT` for partial updates to enable us to just send a `state` update to an existing pin endpoint. This will make sending requests through the Python `requests` library a little more succint, as we'll mainly be interested in changing the state for making our light show.

The JSON model of the `pin` resource is:
```json 
    {
        "id": "Integer(readonly=True, description='The pin unique identifier')",
        "pin_num": "Integer(required=True, description='GPIO pin associated with this endpoint')",
        "color": "String(required=True, description='LED color (multiples allowed)')",
        "name": "String(required=False, description='function name (must be unique)')",
        "state": "String(required=False, description='LED on or off')",
        "direction": "String(required=True, description='in (for opto input) or out (for LED/relay)')",
        "rising_url": "String(required=False, description='URL to PUT on rising edge of input')",
        "falling_url": "String(required=False, description='URL to PUT on falling edge of input')"
    }
```

The HTTP verbs correspond to the typical CRUD operations:
- POST `pins/` : **Create** a new pin
    - where the posted data is JSON looking something like the following:
        ```json
        {
            "pin_num": 23,
            "color": "red",
            "state": "on"
        }
        ```
     - STATUS Code 201 Created - the new resource is returned in the body of the message
     
- GET `pins/`: Fetech (**Read**) all pins stored on the system - STATUS 200 on success
    - e.g:
      ```json
        {
            "id": "1",
            "pin_num": 23,
            "color": "red",
            "state": "on"
        },
        {
            "id": "2",
            "pin_num": 24,
            "color": "blue",
            "state": "off"
        }
        ```
 - GET `pins/<id>`: Fetch a pin given its resource identifier - STATUS 200 on success
    ```json
        {
            "id": "2",
            "pin_num": 24,
            "color": "blue",
            "state": "off"
        }
    ```
 - PUT `pins/<id>` : **Partially Update** a pin given its resource id - STATUS 200 on success
    - You can update a single field, or all fields (except for its uid which is READONLY)
    - e.g. Update the state of pin with id 2:
        - PUT `/pins/2` 
            ```json
            {"state": "off"}
            ```
    
## Breadboard Setup
For this project to work without modifying the code, you will need:
- 9 x (preferably multicolored leds, 3xR,1xG,2xB,3xY in my case)
- 9 x 1k resistors (anything over 100Ω should be fine)
- 1 x breadboard
- 10 x GPIO connecting cables

There are many kits available on Amazon for under $20.
    
### GPIO Pins
This code uses the following configuration:
host = 'http://192.168.1.100/apipath'
```json
{"pin_num": 21, "name": "appr_bell",  "state": "off", "direction": "out"},
{"pin_num": 20, "name": "tc4601",     "state": "off", "direction": "out"},
{"pin_num": 16, "name": "lh-bj-bell", "state": "off", "direction": "out"},
{"pin_num": 12, "name": "lh-bj-lc",   "state": "off", "direction": "out"},
{"pin_num": 25, "name": "lh-bj-tol",  "state": "off", "direction": "out"},
{"pin_num": 24, "name": "lh-th-lc",   "state": "off", "direction": "out"},
{"pin_num": 23, "name": "lh-th-tol",  "state": "off", "direction": "out"},
{"pin_num": 18, "name": "lh-th-bell", "state": "off", "direction": "out"},

{"pin_num": 17, "name": "th-lh-tap",  "direction": "in", "falling_url": "{host}/th-lh-tap/on"},
{"pin_num":  6, "name": "bj-lh-lc",   "direction": "in", "falling_url": "{host}/bj-lh-lc/off",  "rising_url": "{host}/bj-lh-lc/on"},
{"pin_num":  5, "name": "bj-lh-tol",  "direction": "in", "falling_url": "{host}/bj-lh-tol/off", "rising_url": "{host}/bj-lh-tol/on"},
{"pin_num": 22, "name": "th-lh-lc",   "direction": "in", "falling_url": "{host}/th-lh-lc/off",  "rising_url": "{host}/th-lh-lc/on"},
{"pin_num": 27, "name": "th-lh-tol",  "direction": "in", "falling_url": "{host}/th-lh-tol/off", "rising_url": "{host}/th-lh-tol/on"}
```
*Note*: **These pin numbers refer to the GPIO pin numbers, not the generic numbering**
![GPIO](img/rpi_gpio.jpg)

### Schematic
![Schematic](img/schematic.png)

## Running
Once you have your board setup and connected to the Pi and have a connection to your Raspberry Pi, either remotely via SSH(check out my [tutorial](https://www.youtube.com/watch?v=Lr3LLpVBSUk) on SSH access) or locally through a desktop OS on your Raspberry Pi:
- `git clone https://github.com/avcourt/restful-pi2/`
- `cd restful-pi`
- `sudo apt install python3-pip`
- `pip3 install -r requirements.txt`
- `python3 app.py`

If you are running this locally on the pi with a desktop, point your browser at localhost:5000 and you will be greeted by a SwaggerUI to make HTTP requests.

If you're developing remotely through SSH access you will have to create a SSH tunnel from your local machine to the Raspberry Pi in order to access the SwaggerUI. Check out [this](video) video for how to do that.

Once you're tired of manually sending HTTP requests through Swagger(curl), open a Python3 shell in this repo's root directory:
- `python3`
- `import pin_controller.py`
- test out some of the functions:
    - `toggle_color(color: str, state: str)`
    - `switch_all(state: str)`
    - `all_on()`
    - `all_off()`
    - `color_on(color: str)`
    - `color_off(color: str)`
    - `random_stuff()`
    - `rainbow(period: float)`
    - `on_off(period: float)`
    - `wave(period: float)`
    - `single_rand(period: float)`

e.g.:
`pin_controller.color_on("red")`

The functions that have the `period` float paramater have a default value for oscillation. Experiment with different values.

Try making your own functions or messing around with the ones included in this repo.

## Cleanup
`pip3 uninstall -r requirements.txt`

If you have any questions you can join my Discord [server](https://discord.gg/5PfXqqr).
