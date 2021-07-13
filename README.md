# surCamWservo

This repository is a modified clone of surCam (https://github.com/mbroihier/surcam).  The modification adds a hardware interface, servod (https://github.com/mbroihier/servod) via HW.py, that can control a servo attached to a camera so that it can be panned.  The servo I used was a Parallax Standard Servo.

Panning is done by pointing the mouse somewhere in the field of view of the camera scene and then pressing the mouse button.  The servo will attempt to center on that mouse position.

See surCam and servod for installation instructions.  Note that a physical GPIO pin must be configured and wired to the servo control line. The 3.3V PWM control signal should be sufficient for the servo.  Ground and VCC must be connected to the servo.  The ground must be sharred with the Pi ground, but power (5V in my case) should come from an independent source. DON'T use the Pi as the power source for the servo.  The default servod configuration file configures 10 different GPIO pins - one of those pins can be used.

