'''
Surveillance Camera module
'''
import io
import glob
from http import server as httpServer
import os
import socketserver
import time
import threading
from threading import Condition
import picamera
from picamera.array import PiMotionAnalysis

PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Video from rpi2</title>
</head>
<body>
<h1>Recorded video on rpi2</h1>
<img class="base" src="stream.mjpg" width="640" height="480" style="position:absolute; top:60px; left:10px" />
<canvas class="overlay" id="imageArea" width="640" height="480" style="position:absolute; top:60px; left:10px"></canvas>
<div style="position:absolute; top:540px; left:20px">
<list>
</list>
</div>
</body>
</html>
"""

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
                    for index in range(len(buff)-1):
                        if buff[index] == 0xff and buff[index+1] == 0xd8:
                            self.write(buff[segmentStart:index])
                            segmentStart = index
                    self.write(buff[segmentStart:])
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
            beforeList = True
            for line in PAGE.split("\n"):
                page += line + '\n'
                if beforeList:
                    if '<list>' in line:
                        page += '<form action="/index.html" method="post">'
                        beforeList = False
                        for afile in sorted(files):
                            page += '<li><a href=' + afile + '>' + afile + '</a><label for="' + afile + '"></label><input type="checkbox" name="' + afile + '"></li>'
                        page += '<li><a href=camera>camera</a></li>'
                        page += '<button type="submit">Delete Checked Files</button>'
                        page += '</form>'
            content = page.encode('utf-8')
            self.server.output.start(self.server.fileName)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
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
        do_POST - handles POST requests from an HTTP client - they are not expected
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

    def __init__(self, camera, stream):
        '''
        Constructor
        '''
        super(MotionDetector, self).__init__(camera)
        self.stream = stream
        self.lastSampleTime = time.time() - 15.0
        self.consecutiveCount = 0

    def writeFile(self):
        '''
        writeFile - writes a sample of the camera stream to a file
        '''
        fileName = time.strftime("Motion_Detected%Y-%m-%d:%H:%M.mjpeg", time.gmtime())
        print("Writing file:", fileName)
        time.sleep(20)
        self.stream.copy_to(fileName, first_frame=None)
        print("Done")

    def analyze(self, array):
        '''
        analyze a set of frames and determine if something is moving in the frame
        '''
        shape = array['sad'].shape
        size = shape[0] * (shape[1] - 1)
        threshold = size / 100  # 1% of scene changed by more than 254 counts
        # Count the cells where the sum of the absolute difference is greater than 255
        activeCells = (array['sad'] > 255).sum()
        if time.time() - self.lastSampleTime > 20:
            if activeCells > threshold:
                self.consecutiveCount += 1
                if self.consecutiveCount > 2:
                    self.lastSampleTime = time.time()
                    threading.Thread(target=self.writeFile).start()
                    self.consecutiveCount = 0
            else:
                self.consecutiveCount = 0

    def analyse(self, array):
        '''
        analyse a set of frames and determine if something is moving in the frame
        '''
        self.analyze(array)

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
        self.camera = picamera.PiCamera(resolution='VGA', framerate=30)
        self.camera.vflip = True
        self.camera.hflip = True
        self.circularBuffer = picamera.PiCameraCircularIO(self.camera, seconds=15)
        self.motionDetector = MotionDetector(self.camera, self.circularBuffer)
        self.camera.start_recording(self.circularBuffer, format='mjpeg', splitter_port=1)
        self.camera.start_recording(self.output, format='mjpeg', splitter_port=2, resize=(320, 240))
        self.camera.start_recording('/dev/null', format='h264', splitter_port=3,
                                    motion_output=self.motionDetector)

def main():
    '''
    Main program for MJPEG streamer
    '''
    address = ('', 8000)        # use port 8000
    server = StreamingCameraServer(address, StreamingHandler)  # Make a Streaming Camera HTTP server
    try:
        server.serve_forever()      # start the server
    except KeyboardInterrupt:
        print("Gracefully exiting via user request")
    finally:
        server.camera.stop_recording()
if __name__ == '__main__':
    main()
