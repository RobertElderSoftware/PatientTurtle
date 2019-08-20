import signal
import binascii
import socket
import struct
import sys
import select
import time
import datetime
from SloMoConnectionManager import SloMoConnectionManager
from SloMoConnectionManager import SloMoMessage

class SloMoClient(object):
  def __init__(self, debug=False):
    signal.signal(signal.SIGINT, self.cleanup)
    self.done = False
    self.connection_manager = SloMoConnectionManager()
    self.debug = debug

    host = '192.168.0.120'
    port = 3050
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.connect((host, port))
    self.connection_manager.register_socket(self.sock, host, ['message_send_socket'])
    self.connection_manager.register_class_callback('read', 'message_send_socket', self.on_server_event_read)

    #  The current tar file that includes all capture information.
    self.capture_filename = None
    self.current_tar_file = None

  def cleanup(self, signum, frame):
    sys.stdout.write("Caught signal %s. Shutting down.\n" % (str(signum)))
    self.connection_manager.cleanup()
    self.done = True

  def run(self):
    while not self.done:
      self.connection_manager.run(10000)

  def open_new_tar_file(self):
    datetimestr = str(datetime.datetime.now()).replace(":","-").replace(" ", "_")
    self.capture_filename = datetimestr + ".tar"
    self.current_tar_file = open(self.capture_filename, 'w+b')
    print("Opened file " + self.capture_filename + " for writing capture output.")

  def close_tar_file(self):
    self.current_tar_file.close()
    self.current_tar_file = None
    print("Closed file " + self.capture_filename + ".")

  def append_byes_to_tar_file(self, by):
    self.current_tar_file.write(by)
    
  def on_server_message(self, m):
    #print("MSG: " + m.o.decode("utf-8") + " Binary: " + str(m.b))
    message_object = m.get_message_object()
    print(str(message_object))
    if 'end_capture' in message_object:
      self.send_request_results()
    if 'begin_tar_stream' in message_object:
      self.open_new_tar_file()
    if 'data' in message_object:
      if message_object['data'] == 'tar_output':
        self.append_byes_to_tar_file(m.b)
      else:
        # Not implemented
        assert(False)
    if 'end_tar_stream' in message_object:
      self.close_tar_file()
    
  def on_server_event_read(self, fd, socket_details):
    fd = self.connection_manager.sfno(socket_details['socket'])
    if fd:
      while True:
        m = self.connection_manager.try_remove_message(fd)
        if m is None:
          break
        self.on_server_message(m)

  def send_capture_message(self):
    send_fd = self.connection_manager.sfno(self.sock)
    if send_fd:
      rasipraw_args = [
        "-md", "7",
        "-t", "10000",
        "-ts", "/dev/shm/tstamps.csv",
        "-hd0", "/dev/shm/hd0.32k",
        "-h", "64",
        "-w", "640",
        "--vinc", "1F",
        "--fps", "660",
        "-sr", "1",
        "-o", "/dev/shm/out.%06d.raw"
      ]
      r = SloMoMessage({'request_capture': rasipraw_args})
      msg = r.pack_to_binary()
      self.connection_manager.add_to_write_buffer(send_fd, msg)
      print(msg)
    else:
      print("Did not send message: invlid fd.")

  def send_request_results(self):
    send_fd = self.connection_manager.sfno(self.sock)
    if send_fd:
      r = SloMoMessage({'request_results': {'-fps':123}})
      msg = r.pack_to_binary()
      self.connection_manager.add_to_write_buffer(send_fd, msg)
      print(msg)
    else:
      print("Did not send message: invlid fd.")

s = SloMoClient()
s.send_capture_message()
s.run()
