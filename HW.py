#!/usr/bin/python3

import os

class HW():
    '''
    Class that creates a hardware interface to control a Parallax servo
    '''
    def __init__(self):
        '''
        Initialize objects needed
        '''
        self.position = 1500
        self.softStop0 = 1100
        self.softStop1 = 1900
        self.servoBusy = False
        self.servoFifo = open("/dev/servo_fifo", "w")
        self.fdServoFifo = self.servoFifo.fileno()
        self.setPosition(1500)

    def isBusy(self):
        '''
        isBusy - servo is being moved
        '''
        return(self.servoBusy)

    def setPosition(self, timeUSec):
        '''
        setPosition - set the servo to an allowed position
        '''
        self.servoBusy = True
        setting = timeUSec
        if setting >= self.softStop0 and setting <= self.softStop1:
            self.servoFifo.write("1, {}\n".format(timeUSec))
            self.servoFifo.write("9, {}\n".format(timeUSec))
            self.servoFifo.flush()
            self.position = timeUSec
        else:
            print("{} useconds (a setting of {} counts) is beyond the soft stops of the servo".format(timeUSec, setting))
        self.servoBusy = False

    def setPositionFromTo(self, fromTimeUSec, toTimeUSec):
        '''
        setPositionFromTo - move servo from position to position
        '''
        self.servoBusy = True
        setting = fromTimeUSec
        toSetting = toTimeUSec
        if setting < self.softStop0:
            setting = self.softStop0
        else:
            if setting > self.softStop1:
                setting = self.softStop1
        if toSetting < self.softStop0:
            toSetting = self.softStop0
            toTimeUSec = toSetting
        else:
            if toSetting > self.softStop1:
                toSetting = self.softStop1
                toTimeUSec = toSetting
        print("Going from {} to {}".format(fromTimeUSec, toTimeUSec))
        newValue = int(toSetting * 0.10)
        direction = 1 if toSetting >= setting else -1
        oldBeta = 0
        slew = 0
        while setting != toSetting:
            newBeta = int(0.90 * setting)
            if newBeta == oldBeta:
                slew += direction
            setting = newBeta + newValue + slew
            oldBeta = newBeta
            if setting < 1100:
                break
            if setting > 1900:
                break
            print("commanding {}, Beta {}, newValue was {}".format(setting, oldBeta, newValue))
            self.servoFifo.write("0, {}\n".format(setting))
            self.servoFifo.write("1, {}\n".format(setting))
            self.servoFifo.write("2, {}\n".format(setting))
            self.servoFifo.write("3, {}\n".format(setting))
            self.servoFifo.write("4, {}\n".format(setting))
            self.servoFifo.write("5, {}\n".format(setting))
            self.servoFifo.write("6, {}\n".format(setting))
            self.servoFifo.write("7, {}\n".format(setting))
            self.servoFifo.write("8, {}\n".format(setting))
            self.servoFifo.write("9, {}\n".format(setting))
        self.position = toTimeUSec
        self.servoFifo.close()
        self.servoFifo = open("/dev/servo_fifo", "w")
        print("storing new position: {}".format(toTimeUSec))
        self.servoBusy = False
        return(toTimeUSec)
