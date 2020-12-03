# surCam

This repository contains code that implements a surveillance camera using a Raspberry PI (PI 0 W, PI 3, or PI 4) and a PI camera.  


Installation (assuming a Debian/Raspbian buster or better Linux distribution)

  1)  sudo apt-get update
  2)  sudo apt-get upgrade
  3)  sudo apt-get install git python3-pip python3-numpy
  4)  sudo pip3 install picamera
  5)  git clone https://github.com/mbroihier/surcam
      - cd surcam
      - from raspi-config, enable camera if you have not done that before
      - if running on a PI 0, add force_turbo=1 and over_voltage=4 (note warnings about this) to /boot/config.txt file and reboot
      - python3 surveillance_camera.py
  6)  Using a browser, connect to
      - http://<your pi IP address>:8000

