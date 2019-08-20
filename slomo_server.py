import time
import sys
import socket
import select
import subprocess
from SloMoConnectionManager import SloMoConnectionManager
from SloMoConnectionManager import SloMoMessage
import signal

class SloMoServer(object):
  def __init__(self, debug):
    self.done = False

    signal.signal(signal.SIGINT, self.cleanup)

    self.connection_manager = SloMoConnectionManager(debug=debug)

    self.connection_manager.register_listen_socket('0.0.0.0', 3050, ['client_listen_socket'])
    self.connection_manager.register_class_callback('read', 'client_listen_socket', self.on_client_listen_socket_connect)
    self.capture_child = None  # child process for capture command.
    self.tar_child = None  # child process for tar command.
    self.client_socket = None  # Assume we can only support one client at once.

  def cleanup(self, signum, frame):
    sys.stdout.write("Caught signal %s. Shutting down.\n" % (str(signum)))
    self.connection_manager.cleanup()
    self.done = True

  def on_client_close(self, fd, socket_details):
    self.client_socket = None

  def on_client_listen_socket_connect(self, fd, socket_details):
    conn, addr = socket_details['socket'].accept()
    self.connection_manager.register_socket(conn, addr, ['client'])
    self.connection_manager.register_class_callback('read', 'client', self.on_client_event_read)
    self.connection_manager.register_class_callback('close', 'client', self.on_client_close)
    assert(self.client_socket == None)
    self.client_socket = conn
    assert(self.client_socket != None)

  def send_capture_finished_message(self, send_fd, o):
    if send_fd:
      r = SloMoMessage({'capture_finished': o})
      msg = r.pack_to_binary()
      self.connection_manager.add_to_write_buffer(send_fd, msg)
      print(msg)
    else:
      print("Did not send capture_finished message: invlid fd.")

  def on_capture_command_stdout_close(self, fd, socket_details):
    print("Do capture close message: " + str(fd))
    client_fd = self.connection_manager.sfno(self.client_socket)
    r = SloMoMessage({'end_capture': True})
    msg = r.pack_to_binary()
    self.connection_manager.add_to_write_buffer(client_fd, msg)

  def on_capture_command_stdout(self, fd, socket_details):
    sys.stdout.write(str(socket_details['in_bytes'].decode('utf-8')))
    socket_details['in_bytes'] = bytearray(b'')

  def on_capture_command_stderr(self, fd, socket_details):
    sys.stdout.write(str(socket_details['in_bytes'].decode('utf-8')))
    socket_details['in_bytes'] = bytearray(b'')

  def do_capture(self, m):
    print("Doing capture results.")
    try:
      client_fd = self.connection_manager.sfno(self.client_socket)
      r = SloMoMessage({'begin_capture': True})
      msg = r.pack_to_binary()
      self.connection_manager.add_to_write_buffer(client_fd, msg)

      cmd_arr = ["./run-capture.sh", " ".join(m['request_capture'])]
      self.capture_child = subprocess.Popen(cmd_arr, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      stdout_fd = self.capture_child.stdout.fileno()
      stderr_fd = self.capture_child.stderr.fileno()

      self.connection_manager.register_file_descriptor(stdout_fd, ['capture_command_stdout'])
      self.connection_manager.register_class_callback('read', 'capture_command_stdout', self.on_capture_command_stdout)
      self.connection_manager.register_class_callback('close', 'capture_command_stdout', self.on_capture_command_stdout_close)
      self.connection_manager.register_file_descriptor(stderr_fd, ['capture_command_stderr'])
      self.connection_manager.register_class_callback('read', 'capture_command_stderr', self.on_capture_command_stderr)
    except Exception as e:
      print("An exception happend when trying to run command: " + str(cmd_arr) + " "  + str(e) + "\n")
    return ""

  def on_tar_command_stdout_close(self, fd, socket_details):
    client_fd = self.connection_manager.sfno(self.client_socket)
    r = SloMoMessage({'end_tar_stream': True})
    msg = r.pack_to_binary()
    self.connection_manager.add_to_write_buffer(client_fd, msg)

  def on_tar_command_stdout(self, fd, socket_details):
    #sys.stdout.write(str(socket_details['in_bytes']))
    client_fd = self.connection_manager.sfno(self.client_socket)
    if len(socket_details['in_bytes']) > 0:
      r = SloMoMessage({'data': 'tar_output'}, socket_details['in_bytes'])
      msg = r.pack_to_binary()
      self.connection_manager.add_to_write_buffer(client_fd, msg)
      socket_details['in_bytes'] = bytearray(b'')

  def on_tar_command_stderr(self, fd, socket_details):
    sys.stdout.write(str(socket_details['in_bytes'].decode('utf-8')))
    socket_details['in_bytes'] = bytearray(b'')

  def tar_out_results(self, m):
    print("Doing tar out results.")
    try:
      client_fd = self.connection_manager.sfno(self.client_socket)
      print("client_fd is " + str(client_fd))
      r = SloMoMessage({'begin_tar_stream': True})
      msg = r.pack_to_binary()
      self.connection_manager.add_to_write_buffer(client_fd, msg)

      cmd = "cd /dev/shm && tar -cf /dev/stdout *.raw hd0.32k tstamps.csv run_params.txt process-video.sh"
      self.tar_child = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      stdout_fd = self.tar_child.stdout.fileno()
      stderr_fd = self.tar_child.stderr.fileno()

      self.connection_manager.register_file_descriptor(stdout_fd, ['tar_command_stdout'])
      self.connection_manager.register_class_callback('read', 'tar_command_stdout', self.on_tar_command_stdout)
      self.connection_manager.register_class_callback('close', 'tar_command_stdout', self.on_tar_command_stdout_close)
      self.connection_manager.register_file_descriptor(stderr_fd, ['tar_command_stderr'])
      self.connection_manager.register_class_callback('read', 'tar_command_stderr', self.on_tar_command_stderr)
    except Exception as e:
      print("An exception happend when trying to run command: " + str(cmd_arr) + " "  + str(e) + "\n")
    return ""

  def on_client_message(self, fd, m):
    print("Server got message: " + str(m))
    if 'request_capture' in m:
      o = self.do_capture(m)
    if 'request_results' in m:
      o = self.tar_out_results(m)

  def on_client_event_read(self, fd, socket_details):
    fd = self.connection_manager.sfno(socket_details['socket'])
    if fd:
      while True:
        m = self.connection_manager.try_remove_message(fd)
        if m is None:
          break
        self.on_client_message(fd, m.get_message_object())
    
  def run(self):
    while not self.done:
      self.connection_manager.run(10000)


s = SloMoServer(debug=False)
s.run()
