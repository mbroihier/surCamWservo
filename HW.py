#!/usr/bin/python3
import os
import select
import sys
import wiringpi

class HW():
    '''
    Class that creates a hardware interface to control a Parallax servo
    '''
    def __init__(self, timeLow, timeHigh):
        '''
        Initialize wiringPi and objects needed
        '''
        self.HW_CLOCK = 19200000.0
        if os.getuid() == 0:
            wiringpi.wiringPiSetupGpio()
            self.PWMOutputPin = 18
            wiringpi.pinMode(self.PWMOutputPin, wiringpi.PWM_OUTPUT)
            wiringpi.pwmSetMode(wiringpi.PWM_MODE_MS)
            period = (timeLow + timeHigh) / 1000000.0
            self.clock = 200;
            wiringpi.pwmSetClock(self.clock)
            self.range_ = int(period * self.HW_CLOCK / self.clock)
            wiringpi.pwmSetRange(self.range_)
            self.countsPerMicrosecond = self.HW_CLOCK / (self.clock * 1000000.0)
            self.softStop0 = int(self.range_ * 0.001 / 0.021) + 2
            self.softStop1 = int(self.range_ * 0.002 / 0.022) - 2
            self.setPosition(1500)
            print("Servo settings:")
            print("clock: {}, range: {}, countsPerMicrosecond {}".format(self.clock,
                                                                         self.range_, self.countsPerMicrosecond))
            print("softStop0: {}, softStop1 {}".format(self.softStop0, self.softStop1))
            self.servoBusy = False
        else:
            print("This object, built with the HW class, requires root privileges")
            sys.exit(-1)

    def isBusy(self):
        '''
        isBusy - servo is being moved
        '''
        return(self.servoBusy)

    def turnOffPWMPin(self):
        '''
        turnOffPWMPin - zero the PWM setting to disable pulses
        '''
        wiringpi.pwmWrite(self.PWMOutputPin, 0)

    def setPosition(self, timeUSec):
        '''
        setPosition - set the servo to an allowed position
        '''
        self.servoBusy = True
        setting = int(timeUSec * self.countsPerMicrosecond)
        if setting >= self.softStop0 and setting <= self.softStop1:
            wiringpi.pwmWrite(self.PWMOutputPin, setting)
            self.position = timeUSec
        else:
            print("{} useconds (a setting of {} counts) is beyond the soft stops of the servo".format(timeUSec, setting))
        self.servoBusy = False

    def setPositionFromTo(self, fromTimeUSec, toTimeUSec):
        '''
        setPositionFromTo - move servo from position to position
        '''
        self.servoBusy = True
        setting = int(fromTimeUSec * self.countsPerMicrosecond)
        toSetting = int(toTimeUSec * self.countsPerMicrosecond)
        if setting < self.softStop0:
            setting = self.softStop0
        else:
            if setting > self.softStop1:
                setting = self.softStop1
        if toSetting < self.softStop0:
            toSetting = self.softStop0
            toTimeUSec = int(toSetting / self.countsPerMicrosecond)
        else:
            if toSetting > self.softStop1:
                toSetting = self.softStop1
                toTimeUSec = int(toSetting / self.countsPerMicrosecond)
        tick = 0
        delta = -1
        total = setting - toSetting
        if toSetting > setting:
            delta = 1
            total = toSetting - setting
        interval0 = total >> 2
        interval1 = interval0 + interval0 + interval0
        while tick < total:
            if tick < interval0:
                wiringpi.pwmWrite(self.PWMOutputPin, setting)
                select.select([], [], [], 0.020)
            else:
                if tick < interval1:
                    wiringpi.pwmWrite(self.PWMOutputPin, setting)
                else:
                    wiringpi.pwmWrite(self.PWMOutputPin, setting)
                    select.select([], [], [], 0.020)
            #print("setting: {}".format(setting))
            setting += delta
            tick += 1
        self.position = toTimeUSec
        print("storing new position: {}".format(toTimeUSec))
        self.servoBusy = False
        return(toTimeUSec)
