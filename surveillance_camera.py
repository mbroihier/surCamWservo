'''
Surveillance Camera module
'''
import io
import glob
from http import server as httpServer
import json
import numpy as np
import os
import socketserver
import time
import threading
from threading import Condition
import picamera
from picamera.array import PiMotionAnalysis


class StreamingOutput():
    '''
    StreamingOutput class - used to make objects that produce output streams to HTTP clients
    '''
    def __init__(self):
        '''
        Constructor - create buffer and threading related objects
        '''
        self.frame = None
        self.stop = False
        self.buffer = io.BytesIO()
        self.startOfFrame = b"\xff\xd8"
        self.condition = Condition()

    def start(self, fileName):
        '''
        start - starts a thread that reads a file into a stream targeted for a HTTP client
        '''
        with self.condition:
            if self.frame is None:
                threading.Thread(target=self.readFile, args=(fileName,)).start()

    def readFile(self, fileName):
        '''
        readFile - reads a file and divides it into frames for the write method.
        '''
        if fileName == 'default':
            return
        self.stop = False
        try:
            fileHandle = open(fileName, "rb")
            self.write(self.startOfFrame)
            buff = fileHandle.read(10000)
            if not self.stop:
                segmentStart = 0
                while buff:
                    location = buff.find(self.startOfFrame, segmentStart)
                    while location > 0:
                        self.write(buff[segmentStart:location])
                        spin = 0
                        while spin < 1250:
                            spin += 1
                        segmentStart = location
                        location = buff.find(self.startOfFrame, segmentStart+2)
                    self.write(buff[segmentStart:])
                    spin = 0
                    while spin < 1250:
                        spin += 1
                    segmentStart = 0
                    buff = fileHandle.read(10000)
                    if self.stop:
                        print("exiting read file loop")
                        break
            fileHandle.close()
        except FileNotFoundError:
            print("File: {}, was not found".format(fileName))
        with self.condition:
            self.frame = None
            self.condition.notify_all()
            print("Video display finished")

    def write(self, buf):
        '''
        write - write buffer to stream.  The buffers are expected to be MJPEG frames.
        '''
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

    def setStop(self):
        '''
        setStop - stop readFile thread
        '''
        self.stop = True

class StreamingHandler(httpServer.BaseHTTPRequestHandler):
    '''
    StreamingHandler - class that will build an object that implements a basic HTTP server
    '''

    def do_GET(self):
        '''
        do_GET - handles GET requests from an HTTP client
        '''
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()

        elif self.path == '/index.html':
            files = glob.glob('*.mjpeg')
            page = ""
            page += '<!DOCTYPE html>\n'
            page += '<html lang="en">\n'
            page += '<head>\n'
            page += '<meta charset="utf-8">\n'
            page += '<meta http-equiv="Pragma" content="no-cache">\n'
            page += '<link rel="stylesheet" href="style.css"/>\n'
            page += '<title>SurCam</title>\n'
            page += '</head>\n'
            page += '<body>\n'
            if self.server.fileName == 'default':
                page += '<h1>Video from surCam ' + self.server.defaultsObject.getCameraName() + '</h1>\n'
            else:
                page += '<h2>' + self.server.fileName + '</h2>\n'
            page += '<img class="base" src="stream.mjpg" width="640" height="480" style="position:absolute; top:60px; left:10px" />\n'
            page += '<canvas class="overlay" id="imageArea" width="640" height="480" style="position:absolute; top:60px; left:10px"></canvas>\n'
            page += '<div style="position:absolute; top:540px; left:20px">\n'
            page += '<h2>Video Sources</h2>\n'
            page += '<ul>\n'
            page += '<form action="/index.html" method="post" id="deletes">'
            for afile in sorted(files):
                page += '<li><a href=' + afile + '>' + afile + '</a><label for="' + afile + '"></label><input type="checkbox" name="' + afile + '"></li>'
            page += '<li><a href=camera>camera</a></li>'
            page += '</form>'
            page += '</ul>'
            page += '<button type="submit" form="deletes">Delete Checked Files</button>'
            page += '<h2>Camera Settings</h2>'
            page += '<ul>'
            page += '<li>'
            page += '<form action="/index.html" method="post">'
            page += '<label for="camera1">Shutter Speed:</label><input pattern="[0-9]{1,7}" type="text" name="Shutter"'
            page += ' placeholder="' + "{:7d}".format(self.server.camera.exposure_speed) + '" maxlength="8" size="8"> microseconds</li>'
            page += '</form>'
            page += '<li>'
            page += '<form action="/index.html" method="post">'
            page += '<label for="camera2">Frame Rate:</label><input pattern="[0-9]{1,2}" type="text" name="FrameRate"'
            page += ' placeholder="' + "{:2d}".format(int(float(self.server.camera.framerate.numerator)/float(self.server.camera.framerate.denominator))) + '" maxlength="3" size="3"> frames / second</li>'
            page += '</form>'
            page += '</ul>'
            page += '<form action="/index.html" method="post">'
            page += '<h2>Motion Detection Sensitivity</h2>'
            page += '<label for="Attenuation">Least(99.99) / Most (0.01)</label><input pattern="[0-9]{1,2}\.[0-9]{1,2}" type="text" name="Attenuation"'
            page += ' placeholder="' + "{:5.2f}".format(self.server.motionDetector.sensitivity) + '" maxlength="6" size="6">'
            page += '</form>'
            page += '</div>\n'
            page += '</body>\n'
            page += '</html>\n'
            content = page.encode('utf-8')
            self.server.output.start(self.server.fileName)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/style.css':
            fileObject = open('./style.css', 'r')
            content = ""
            for line in fileObject:
                content += line
            content = content.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/css')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                done = False
                while not done:
                    if not self.server.fileName is None:
                        with self.server.output.condition:
                            self.server.output.condition.wait()
                            frame = self.server.output.frame
                        done = frame is None
                        if not done:
                            self.wfile.write(b'--FRAME\r\n')
                            self.send_header('Content-Type', 'image/jpeg')
                            self.send_header('Content-Length', len(frame))
                            self.end_headers()
                            self.wfile.write(frame)
                            self.wfile.write(b'\r\n')
                print("Streaming has terminated")
            except BrokenPipeError:
                print('Removed streaming client')
        elif 'mjpeg' in self.path:
            if self.server.fileName == 'default':
                self.server.camera.stop_recording(splitter_port=2)
                with self.server.output.condition:
                    self.server.output.frame = None
            else:
                with self.server.output.condition:
                    self.server.output.setStop()
                    self.server.output.frame = None
            self.server.fileName = self.path[1:]
            print("Set file name to:", self.server.fileName)
            self.send_response(302)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/camera':
            if self.server.fileName != 'default':
                with self.server.output.condition:
                    self.server.output.setStop()
                    self.server.output.frame = None
                self.server.fileName = 'default'
                self.server.camera.start_recording(self.server.output, format='mjpeg',
                                                   splitter_port=2, resize=(320, 240))
                print("Set file name to:", self.server.fileName)
            self.send_response(302)
            self.send_header('Location', '/index.html')
            self.end_headers()
        else:
            self.send_error(404)
            self.end_headers()

    def do_POST(self):
        '''
        do_POST - handles POST requests from an HTTP client
        '''
        print("Processing post:", self.path)
        if self.path == '/index.html':
            length = int(self.headers['Content-Length'])
            line = self.rfile.read(length)
            line = line.decode('utf-8')
            filesToDelete = line.split('=on')
            for fileName in filesToDelete:
                if fileName:
                    conditionedFileName = fileName.strip('&').replace('%3A', ':')
                    if "Attenuation" in fileName:
                        newValue = fileName.replace("Attenuation=", "")
                        if newValue == "":
                            newValue = "99.99"
                        print("Setting sensitivity level to", newValue)
                        self.server.motionDetector.setSensitivity(float(newValue))
                        self.server.motionDetector.defaultsObject.setSensitivity(float(newValue))
                        time.sleep(1.0)
                    elif "Shutter" in fileName:
                        newValue = fileName.replace("Shutter=", "")
                        if newValue == "":
                            newValue = "0"
                        print("Setting shutter speed to", newValue)
                        self.server.camera.shutter_speed = int(newValue)
                        self.server.defaultsObject.setShutter_speed(int(newValue))
                        time.sleep(1.0)
                    elif "FrameRate" in fileName:
                        newValue = fileName.replace("FrameRate=", "")
                        if newValue == "":
                            newValue = str(self.server.camera.framerate)
                        print("Setting framerate to", newValue)
                        self.server.framerate = int(newValue)
                        self.server.defaultsObject.setFramerate(int(newValue))
                        self.server.restartCamera()
                        time.sleep(3.0)
                    else:
                        print("Request to delete file:", conditionedFileName)
                        try:
                            os.remove(conditionedFileName)
                        except FileNotFound:
                            print("Error on attempt to delete", conditionedFileName)
            self.send_response(302)
            self.send_header('location', 'index.html')
            self.end_headers()


class MotionDetector(PiMotionAnalysis):
    '''
    MotionDector - class derived from PiMotionAnalysis that implements a motion detection algorithm
    '''

    def __init__(self, camera, stream, defaultsObject):
        '''
        Constructor
        '''
        super(MotionDetector, self).__init__(camera)
        self.stream = stream
        self.lastSampleTime = time.time() - 15.0
        self.consecutiveCount = 0
        self.writeThreadActive = False
        self.defaultsObject = defaultsObject
        self.sensitivity = self.defaultsObject.getSensitivity()
        self.mask = self.defaultsObject.mask

    def writeFile(self):
        '''
        writeFile - writes a sample of the camera stream to a file
        '''
        fileName = time.strftime("Motion_Detected%Y-%m-%d:%H:%M:%S.mjpeg", time.gmtime())
        print("Writing file:", fileName)
        time.sleep(15)
        self.stream.copy_to(fileName, first_frame=None)
        print("Done")
        self.writeThreadActive = False

    def analyze(self, array):
        '''
        analyze a set of frames and determine if something is moving in the frame
        '''
        if not self.writeThreadActive:
            shape = array['sad'].shape
            size = shape[0] * (shape[1] - 1)
            threshold = size / 100 * self.sensitivity # 1% of scene changed by more than 254 counts
            # Count the cells where the sum of the absolute difference is greater than 255
            activeCells = ((array['sad'] * self.mask) > 255).sum()
            if time.time() - self.lastSampleTime > 15:
                if activeCells > threshold:
                    self.consecutiveCount += 1
                    if self.consecutiveCount > 2:
                        self.lastSampleTime = time.time()
                        self.writeThreadActive = True
                        threading.Thread(target=self.writeFile).start()
                        self.consecutiveCount = 0
                        print("current threshold:", threshold, " activeCells:", activeCells, " sensitivity:", self.sensitivity)
                else:
                    self.consecutiveCount = 0

    def analyse(self, array):
        '''
        analyse a set of frames and determine if something is moving in the frame
        '''
        self.analyze(array)

    def setSensitivity(self, value):
        '''
        setter for sensitivity
        '''
        self.sensitivity = value

class Background():
    '''
    A background thread that does camera data collection
    '''
    def __init__(self, cameraObject):
        '''
        Constructor
        '''
        self.camera = cameraObject
        self.terminate = False

    def collector(self):
        '''
        Process that collects and records the desired data
        '''
        sampleCount = 0
        redGainSum = 0.0
        blueGainSum = 0.0
        analogueGainSum = 0.0
        while not self.terminate:
            time.sleep(1.0)
            redGain = float(self.camera.awb_gains[0].numerator) / float(self.camera.awb_gains[0].denominator)
            blueGain = float(self.camera.awb_gains[1].numerator) / float(self.camera.awb_gains[1].denominator)
            redGainSum += redGain
            blueGainSum += blueGain
            analogueGainSum += float(self.camera.analog_gain)
            sampleCount += 1
            if sampleCount >= 60:  # one minute
                print("Time: {}, White Balance Gains: {:3.1f}, {:3.1f}".format(time.time(), redGainSum/60.0, blueGainSum/60.0))
                print("Time: {}, Analogue Gain: {:3.1f}".format(time.time(), analogueGainSum/60.0))
                sampleCount = 0
                redGainSum = 0.0
                blueGainSum = 0.0
                analogueGainSum = 0.0

    def terminateBackground(self):
        '''
        Stop the thread
        '''
        self.terminate = True

class HandleDefaults():
    '''
    Read and write defaults to JSON file
    '''
    def __init__(self):
        '''
        Constructor - get initial defaults if they exist, otherwise set them
        '''
        self.mask = np.ones((30, 41), dtype = int)
        for row in range(30):
            for col in range(41):
                if row < 25:
                    self.mask[row][col] = 0
                else:
                    if col > 39:
                        self.mask[row][col] = 0
        self.defaults = {}
        try:
            fileHandle = open("./surCamDefaults.json", "r")
            self.defaults = json.load(fileHandle)
            self.mask = np.asarray(self.defaults['mask']).reshape(30, 41)
            fileHandle.close()
        except FileNotFoundError:
            print("Defaults file was not found - setting")
            
            self.defaults = { 'cameraName' : 'Alpha', 'framerate' : 15, 'vflip' : True, 'hflip' : True,
                              'iso' : 800, 'shutter_speed' : 0, 'sensitivity' : 99.99, 'mask' : self.mask.tolist() }
            self.write()

    def getCameraName(self):
        '''
        getter - cameraName
        '''
        return self.defaults['cameraName']
    
    def getFramerate(self):
        '''
        getter - framerate
        '''
        return self.defaults['framerate']
    
    def getVflip(self):
        '''
        getter - vflip
        '''
        return self.defaults['vflip']
    
    def getHflip(self):
        '''
        getter - hflip
        '''
        return self.defaults['hflip']
    
    def getISO(self):
        '''
        getter - ISO
        '''
        return self.defaults['iso']
    
    def getShutter_speed(self):
        '''
        getter - shutter_speed
        '''
        return self.defaults['shutter_speed']
    
    def getSensitivity(self):
        '''
        getter - sensitivity
        '''
        return self.defaults['sensitivity']

    def setCameraName(self, value):
        '''
        setter - cameraName
        '''
        self.defaults['cameraName'] = value
        self.write()
    
    def setFramerate(self, value):
        '''
        setter - framerate
        '''
        self.defaults['framerate'] = value
        self.write()
    
    def setVflip(self, value):
        '''
        setter - vflip
        '''
        self.defaults['vflip'] = value
        self.write()
    
    def setHflip(self, value):
        '''
        setter - hflip
        '''
        self.defaults['hflip'] = value
        self.write()
    
    def setISO(self, value):
        '''
        setter - ISO
        '''
        self.defaults['iso'] = value
        self.write()
    
    def setShutter_speed(self, value):
        '''
        setter - shutter_speed
        '''
        self.defaults['shutter_speed'] = value
        self.write()
    
    def setSensitivity(self, value):
        '''
        setter - sensitivity
        '''
        self.defaults['sensitivity'] = value
        self.write()

    def write(self):
        '''
        write - update defaults file
        '''
        fileHandle = open("./surCamDefaults.json", "w")
        jsonString = json.dump(self.defaults, fileHandle)
        fileHandle.close()
            
class StreamingCameraServer(socketserver.ThreadingMixIn, httpServer.HTTPServer):
    '''
    A Streaming Camera HTTP server class that iterfaces the camera to a HTTP server
    '''
    allow_reuse_address = True
    daemon_threads = True
    def __init__(self, address, _class):
        super(StreamingCameraServer, self).__init__(address, _class)
        self.fileName = 'default'
        self.output = StreamingOutput()
        self.defaultsObject = HandleDefaults()
        self.framerate = self.defaultsObject.getFramerate()
        self.camera = picamera.PiCamera(resolution='VGA', framerate=self.framerate)
        self.camera.vflip = self.defaultsObject.getVflip()
        self.camera.hflip = self.defaultsObject.getHflip()
        self.camera.iso = self.defaultsObject.getISO()
        self.camera.shutter_speed = self.defaultsObject.getShutter_speed()
        self.camera.sensor_mode = 1
        self.camera.exposure_mode = 'fixedfps'
        self.circularBuffer = picamera.PiCameraCircularIO(self.camera, seconds=15)
        self.motionDetector = MotionDetector(self.camera, self.circularBuffer, self.defaultsObject)
        self.camera.start_recording(self.circularBuffer, format='mjpeg', splitter_port=1)
        self.camera.start_recording(self.output, format='mjpeg', splitter_port=2, resize=(320, 240))
        self.camera.start_recording('/dev/null', format='h264', splitter_port=3,
                                    motion_output=self.motionDetector)
        self.background = Background(self.camera)

    def restartCamera(self):
        self.camera.stop_recording(splitter_port=1)
        if self.fileName == 'default':
            self.camera.stop_recording(splitter_port=2)
        self.camera.stop_recording(splitter_port=3)
        time.sleep(1.0)
        self.camera.framerate = self.framerate
        self.camera.start_recording(self.circularBuffer, format='mjpeg', splitter_port=1)
        if self.fileName == 'default':
            self.camera.start_recording(self.output, format='mjpeg', splitter_port=2, resize=(320, 240))
        self.camera.start_recording('/dev/null', format='h264', splitter_port=3,
                                    motion_output=self.motionDetector)

    def stopCamera(self):
        self.camera.stop_recording(splitter_port=1)
        if self.fileName == 'default':
            self.camera.stop_recording(splitter_port=2)
        self.camera.stop_recording(splitter_port=3)

def main():
    '''
    Main program for MJPEG streamer
    '''
    address = ('', 8000)        # use port 8000
    server = StreamingCameraServer(address, StreamingHandler)  # Make a Streaming Camera HTTP server
    backgroundThread = threading.Thread(target=server.background.collector)
    backgroundThread.start()
    print("Background collection started")
    try:
        server.serve_forever()      # start the server
    except KeyboardInterrupt:
        print("Gracefully exiting via user request")
    finally:
        server.stopCamera()
    server.background.terminateBackground()
    backgroundThread.join()
if __name__ == '__main__':
    main()
