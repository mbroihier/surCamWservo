'''
Surveillance video module
'''
import io
import glob
from http import server as httpServer
import os
import re
import socketserver
import time
import threading
from threading import Condition

sessionIDPattern = re.compile(r'sessionID=(\d+)')

class StreamingHandler(httpServer.BaseHTTPRequestHandler):
    '''
    StreamingHandler - class that will build an object that implements a basic HTTP server
    '''

    def do_GET(self):
        '''
        do_GET - handles GET requests from an HTTP client
        '''
        print("GET from ", self.client_address)
        print(self.path)
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()

        elif '/index.html' in self.path and not 'mjpg' in self.path and not 'mjpeg' in self.path and not 'playbackStyle.css' in self.path:
            print("Processing an index page")
            files = glob.glob('*.mjpeg')
            page = ""
            beforeList = True
            startFrame = 1
            stopFrame = 450
            speedFactor = 1.0
            referenceID = 0
            if 'sessionID' in self.path:
                referenceID = self.path.replace("/index.html/sessionID=", "")
                referenceID = int(referenceID)
            filelist = ""
            first = True
            if files:
                for afile in sorted(files):
                    if first:
                        first = False
                        referenceID = self.server.sessionManager.initializeSessionObject(afile, referenceID)
                    filelist += '<li><a href=' + afile + '/sessionID=' +str(self.server.sessionManager.sessions[referenceID]['sessionID']) + '>' + afile + '</a></li>'
                print("do_GET - waiting for interfaceObject access")
                with self.server.sessionManager.sessions[referenceID]['condition']:  # interface object access
                    startFrame = self.server.sessionManager.sessions[referenceID]['startFrame']
                    stopFrame = self.server.sessionManager.sessions[referenceID]['stopFrame']
                    speedFactor = self.server.sessionManager.sessions[referenceID]['speedFactor']
                    self.server.sessionManager.sessions[referenceID]['condition'].notify()
                    self.server.sessionManager.startVideoFileReadThread(referenceID)
                print("do_GET - got information from interfaceObject")
                page = '<!DOCTYPE html>'
                page += '<html lang="en">'
                page += '<head>'
                page += '<meta charset="utf-8">'
                page += '<link rel="stylesheet" href="playbackStyle.css"/>'
                page += '<title>' + self.server.sessionManager.sessions[referenceID]['theThread'].fileName + '</title>'
                page += '</head>'
                page += '<body>'
                page += '<h1>' + self.server.sessionManager.sessions[referenceID]['theThread'].fileName +'</h1>'
                page += '<img class="base" src="stream.mjpg/sessionID=' + str(referenceID) + '" width="640" height="480" style="position:absolute; top:60px; left:10px" />'
                page += '<canvas class="overlay" id="imageArea" width="640" height="480" style="position:absolute; top:60px; left:10px"></canvas>'
                page += '<div style="position:absolute; top:540px; left:20px">'
                page += '<h2>Video Sources</h2>'
                page += '<ul>'
                page += filelist
                page += '</ul>'
                page += '<h2>Playback Controls</h2>'
                page += '<ul>'
                page += '<li>'
                page += '<form action="/index.html" method="post">'
                page += '<label for="LoopStartFrame">Loop Start Frame</label><input pattern="[0-9]{1,3}" type="text" name="LoopStartFrame"'
                page += ' placeholder="' + "{:3d}".format(startFrame) + '" maxlength="6" size="6">'
                page += '<input type="submit" name="sessionid" value="'+ str(self.server.sessionManager.sessions[referenceID]['sessionID']) + '" style="display:none;">'
                page += '</form>'
                page += '</li>'
                page += '<li>'
                page += '<form action="/index.html" method="post">'
                page += '<label for="LoopStopFrame">Loop Stop Frame</label><input pattern="[0-9]{1,3}" type="text" name="LoopStopFrame"'
                page += ' placeholder="' + "{:3d}".format(stopFrame) + '" maxlength="6" size="6">'
                page += '<input type="submit" name="sessionid" value="'+ str(self.server.sessionManager.sessions[referenceID]['sessionID']) + '" style="display:none;">'
                page += '</form>'
                page += '</li>'
                page += '<li>'
                page += '<form action="/index.html" method="post">'
                page += '<label for="SpeedFactor">Speed Factor(> 1 faster, < 1 slower)</label>'
                page += '<input pattern="[0-9]{1,2}\.[0-9]{1,2}" type="text" name="SpeedFactor"'
                page += ' placeholder="' + "{:5.2f}".format(speedFactor) + '" maxlength="6" size="6">'
                page += '<input type="submit" name="sessionid" value="'+ str(self.server.sessionManager.sessions[referenceID]['sessionID']) + '" style="display:none;">'
                page += '</form>'
                page += '</li>'
                page += '</ul>'
                page += '</div>'
                page += '</body>'
                page += '</html>'
            else:
                page += 'No video files'
            content = page.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif '/playbackStyle.css' in self.path:
            fileObject = open('./playbackStyle.css', 'r')
            content = ""
            for line in fileObject:
                content += line
            content = content.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/css')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif '/stream.mjpg' in self.path:
            referenceID = 1
            matchObject = sessionIDPattern.search(self.path)
            if matchObject:
                referenceID = int(matchObject.group(1))
                print("Starting a stream with session ID:", referenceID)
            else:
                print("Error -- starting a stream without the expected session ID  - defaulted to 1")
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                done = False
                print("HTTP server accepting a video stream")
                while not done:
                    with self.server.sessionManager.condition: # sessions object access
                        with self.server.sessionManager.sessions[referenceID]['theThread'].condition: # thread object access
                            result = self.server.sessionManager.sessions[referenceID]['theThread'].condition.wait(3.0)
                            frame = self.server.sessionManager.sessions[referenceID]['theThread'].frame
                            if not result:
                                print("Wait timeout")
                                frame = None
                            self.server.sessionManager.sessions[referenceID]['theThread'].condition.notifyAll()
                        self.server.sessionManager.condition.notifyAll()
                    done = frame is None
                    if not done:
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', len(frame))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                print("HTTP server finished with video stream")
            except BrokenPipeError:
                print('Removing streaming client')
                with self.server.sessionManager.sessions[referenceID]['theThread'].condition: # thread object access
                    self.server.sessionManager.sessions[referenceID]['theThread'].setStop()
                    self.server.sessionManager.sessions[referenceID]['theThread'].condition.notify()
                print('Removed streaming client')
        elif 'mjpeg' in self.path:
            referenceID = 1
            if 'sessionID' in self.path:
                (fileName, referenceID) = self.path.split("/sessionID=")
                fileName = fileName.split('/')[-1]
                print(fileName, referenceID, self.path)
                referenceID = int(referenceID)
                with self.server.sessionManager.sessions[referenceID]['theThread'].condition:
                    self.server.sessionManager.sessions[referenceID]['theThread'].setStop()
                    self.server.sessionManager.sessions[referenceID]['theThread'].frame = None
                    self.server.sessionManager.sessions[referenceID]['theThread'].setFileName(fileName)
                    self.server.sessionManager.sessions[referenceID]['theThread'].condition.notify()
                print("Set file name in session:", referenceID, ", to:", fileName)
            else:
                print("Error -- a session ID was expected while processing new a new file selection  - defaulted to 1")
            self.send_response(302)
            self.send_header('Location', '/index.html/sessionID=' + str(referenceID))
            self.end_headers()
        else:
            self.send_error(404)
            self.end_headers()

    def do_POST(self):
        '''
        do_POST - handles POST requests from an HTTP client
        '''
        print("Processing post:", self.path)
        print("Post from", self.client_address)
        print(self.headers)
        print(self.rfile)
        if self.path == '/index.html':
            length = int(self.headers['Content-Length'])
            line = self.rfile.read(length)
            line = line.decode('utf-8')
            print(line)
            filesToDelete = line.split('&')
            newStartFrame = None
            newStopFrame = None
            newSpeedFactor = None
            referenceID = 0
            for fileName in filesToDelete:
                if fileName:
                    conditionedFileName = fileName.strip('&').replace('%3A', ':')
                    if "LoopStartFrame" in fileName:
                        newValue = fileName.replace("LoopStartFrame=", "")
                        print("Setting startFrame to", newValue)
                        if newValue != "":
                            newStartFrame = int(newValue)
                    elif "LoopStopFrame" in fileName:
                        newValue = fileName.replace("LoopStopFrame=", "")
                        print("Setting stopFrame to", newValue)
                        if newValue != "":
                            newStopFrame = int(newValue)
                    elif "SpeedFactor" in fileName:
                        newValue = fileName.replace("SpeedFactor=", "")
                        print("Setting speedFactor to", newValue)
                        if newValue != "":
                            newSpeedFactor = float(newValue)
                    elif "sessionid" in fileName:
                        newValue = fileName.replace("sessionid=", "")
                        print("Setting sessionid to", newValue)
                        referenceID = int(newValue)
                    else:
                        print("Unknown request:", conditionedFileName)
            print("do_POST -- waiting for access to the thread object")
            with self.server.sessionManager.sessions[referenceID]['theThread'].condition:
                self.server.sessionManager.sessions[referenceID]['theThread'].setStop()
                self.server.sessionManager.sessions[referenceID]['theThread'].condition.notify()
            print("do_POST -- got access to the thread object")
            print("do_POST -- waiting for access to interface object")
            with self.server.sessionManager.sessions[referenceID]['condition']:
                if not newStartFrame is None:
                    self.server.sessionManager.sessions[referenceID]['startFrame'] = newStartFrame
                elif not newStopFrame is None:
                    self.server.sessionManager.sessions[referenceID]['stopFrame'] = newStopFrame
                elif not newSpeedFactor is None:
                    self.server.sessionManager.sessions[referenceID]['speedFactor'] = newSpeedFactor
                self.server.sessionManager.sessions[referenceID]['condition'].notify()
            print("do_POST -- got access to the interface object")
            self.send_response(302)
            self.send_header('location', 'index.html/sessionID=' + str(referenceID))
            self.end_headers()


class VideoFileThread(threading.Thread):
    '''
    Video File Thread class - used to make objects that produce output streams to HTTP clients
    '''
    def __init__(self, fileName, interfaceObject):
        '''
        Constructor - create buffer and threading related objects
        '''
        super(VideoFileThread, self).__init__()
        self.fileName = fileName
        self.interfaceObject = interfaceObject
        self.stop = False
        self.startOfFrame = b"\xff\xd8"
        self.buffer = io.BytesIO()
        self.condition = Condition()  # for controlling access to thread
        self.frame = None
        self.notStarted = True

    def run(self):
        '''
        runs - starts a thread that reads a file into a stream targeted for a HTTP client
        '''
        startFrame = 1
        stopFrame = 450
        speedFactor = 1
        sessionID = 1
        governor  = Condition()
        with self.interfaceObject['condition']:
            startFrame = self.interfaceObject['startFrame']
            stopFrame = self.interfaceObject['stopFrame']
            speedFactor = self.interfaceObject['speedFactor']
            sessionID = self.interfaceObject['sessionID']
            self.interfaceObject['condition'].notify()

        print("Starting Session:", sessionID)
        try:
            while not self.stop:
                framesProcessed = 0
                print("starting read of:", self.fileName, ", for session:", sessionID)
                fileHandle = open(self.fileName, "rb")
                buff = fileHandle.read(10000)
                segmentStart = 0
                while buff:
                    location = buff.find(self.startOfFrame, segmentStart)
                    while location > 0:
                        framesProcessed += 1
                        if framesProcessed >= startFrame:
                            self.write(buff[segmentStart:location])
                            if framesProcessed > stopFrame:
                                print("written last frame to display")
                                break
                            with governor:
                                governor.wait(0.00396 / speedFactor)
                                governor.notify()
                        segmentStart = location
                        location = buff.find(self.startOfFrame, segmentStart+2)
                    if framesProcessed > stopFrame:
                        print("No need to process more frames - terminate this loop")
                        buff = 0
                        break
                    if framesProcessed >= startFrame:
                        self.write(buff[segmentStart:])
                        with governor:
                            governor.wait(0.00396 / speedFactor)
                            governor.notify()
                    segmentStart = 0
                    buff = fileHandle.read(10000)
                    if self.stop:
                        print("told to stop - exiting read file loop")
                        break
                print("closing file")
                fileHandle.close()
                print("Frames processed:", framesProcessed)
        except FileNotFoundError:
            print("File: {}, was not found".format(self.fileName))
        print("Video display finished")
        print("Ending Session:", sessionID)

    def write(self, buf):
        '''
        write - write buffer to stream.  The buffers are expected to be MJPEG frames.
        '''
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition: # thread object access
                self.frame = self.buffer.getvalue()
                self.condition.notify()
            self.buffer.seek(0)
        return self.buffer.write(buf)

    def setFileName(self, fileName):
        '''
        Set the file name to process
        '''
        self.fileName = fileName
        
    def setStop(self):
        '''
        setStop - stop readFile thread
        '''
        print("Stopping file read thread")
        self.stop = True

class SessionManager():
    '''
    Class for making a HTTP client session manager
    '''
    sessions = {}
    nextSessionID = 1
    condition = Condition()  # for rendevous of sessions object
    def __init__(self):
        '''
        Constructor
        '''

    def initializeSessionObject(self, fileName, referenceID):
        '''
        Initialize a session entry
        '''
        print("initializeSessionObject - waiting for sessions object access")
        with self.condition: # sessions object
            print("initializeSessionObject - Setting the conditions for session")
            if not referenceID in self.sessions:
                self.sessions[self.nextSessionID] = {
                    'startFrame' : 1,
                    'stopFrame' : 450,
                    'speedFactor' : 1.0,
                    'condition' : Condition (),  # for controlling access to interface objects
                    'sessionID' : self.nextSessionID }
                referenceID = self.nextSessionID
                self.nextSessionID += 1
                self.sessions[referenceID]['theThread'] = VideoFileThread(fileName, self.sessions[referenceID])
            else:
                with self.sessions[referenceID]['theThread'].condition:
                    self.sessions[referenceID]['theThread'].setStop()
                    self.sessions[referenceID]['theThread'].condition.notifyAll()
                    oldFileName = self.sessions[referenceID]['theThread'].fileName
                    self.sessions[referenceID]['theThread'] = VideoFileThread(oldFileName, self.sessions[referenceID])
            self.condition.notify()
        print("initializeSessionObject - got sessions object access")
        return referenceID

    def startVideoFileReadThread(self, referenceID):
        '''
        Starts a thread and puts it in the sessions dictionary
        '''
        with self.sessions[referenceID]['theThread'].condition:
            if self.sessions[referenceID]['theThread'].notStarted:
                self.sessions[referenceID]['theThread'].start()
                self.sessions[referenceID]['theThread'].notStarted = False
            self.sessions[referenceID]['theThread'].condition.notifyAll()

    def stopVideoThread(self, session):
        '''
        Stops the video streaming
        '''
        self.sessions[session]['theThread'].setStop()


class StreamingFileServer(socketserver.ThreadingMixIn, httpServer.HTTPServer):
    '''
    A Streaming File Class for HTTP server
    '''
    allow_reuse_address = True
    daemon_threads = True
    def __init__(self, address, _class):
        super(StreamingFileServer, self).__init__(address, _class)
        self.sessionManager = SessionManager()

def main():
    '''
    Main program for MJPEG streamer
    '''
    address = ('', 8000)        # use port 8000
    server = StreamingFileServer(address, StreamingHandler)  # Make a Streaming Video HTTP server
    try:
        server.serve_forever()      # start the server
    except KeyboardInterrupt:
        print("Gracefully exiting via user request")
    finally:
        pass
if __name__ == '__main__':
    main()
