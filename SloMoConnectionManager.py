import socket
import select
import sys
import struct
import json
import os
import traceback

if sys.version_info < (3, 0):
    sys.stdout.write("I only tested this script with python 3, so just to be safe use that.\n")
    sys.exit(1)

SLOMO_HELLO_MESSAGE = 1

class SloMoMessage(object):
  def __init__(self, o, b=bytearray()):
    self.o = o
    self.b = b
    
  def pack_to_binary(self):
    obj_enc = bytearray(json.dumps(self.o).encode())
    return struct.pack("II", len(obj_enc), len(self.b)) + obj_enc + self.b

  def get_message_object(self):
    return json.loads(self.o.decode("utf-8"))

class SloMoConnectionManager(object):
  def __init__(self, debug=False, sigint_callback=None):
    self.sigint_callback = sigint_callback
    self.recv_size = 1048576
    self.EXCEPTION_FLAGS = select.POLLERR
    self.READ_FLAGS = select.POLLHUP | select.POLLIN | select.POLLPRI
    self.WRITE_FLAGS = select.POLLOUT
    self.debug = debug
    self.socket_map = {}
    self.poller = select.poll()
    self.class_callbacks = {
      'close' : {},
      'read' : {},
      'write' : {},
      'exception' : {}
    }

  def sfno(self, s):
    #  Safe fileno function that doesn't casuse exceptions.
    try:
      fno = s.fileno()
      if fno < 0:
        return None
      else:
        return fno
    except Exception as e:
      return None

  def cleanup(self):
    sys.stdout.write("Shutting down closing all %u sockets.\n" % (len(self.socket_map)))
    for s in self.socket_map:
      try:
        sys.stdout.write("Closing fd %u.\n" % (s))
        self.socket_map[s]['socket'].close()
      except Exception as e:
        pass

    if self.sigint_callback is not None:
      sigint_callback()
    
  def register_file_descriptor(self, fd, classes):
    initial_event_mask = self.READ_FLAGS | self.EXCEPTION_FLAGS
    self.poller.register(fd, initial_event_mask)
    print("Registered file descriptor fd " + str(fd))
    self.socket_map[fd] = {
      'is_listen_socket': False,
      'is_socket': False,
      'event_mask': initial_event_mask,
      'out_bytes': bytearray(b''),
      'in_bytes': bytearray(b''),
      'socket': None,
      'address': None,
      'port': None,
      'classes': classes
    }

  def register_listen_socket(self, address, port, classes):
    initial_event_mask = self.READ_FLAGS | self.EXCEPTION_FLAGS
    listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.poller.register(self.sfno(listen_socket), initial_event_mask)
    print("Registered listen fd " + str(self.sfno(listen_socket)))
    self.socket_map[self.sfno(listen_socket)] = {
      'is_listen_socket': True,
      'is_socket': True,
      'event_mask': initial_event_mask,
      'out_bytes': bytearray(b''),
      'in_bytes': bytearray(b''),
      'socket': listen_socket,
      'address': address,
      'port': port,
      'classes': classes
    }
    listen_socket.bind((address, port))
    listen_socket.listen(10)  #  Backlog of up to 10 new connections.

  def register_socket(self, sock, address, classes):
    initial_event_mask = self.READ_FLAGS | self.WRITE_FLAGS | self.EXCEPTION_FLAGS
    self.poller.register(self.sfno(sock), initial_event_mask)
    print("Registered socket fd " + str(self.sfno(sock)))
    self.socket_map[self.sfno(sock)] = {
      'is_listen_socket': False,
      'is_socket': True,
      'event_mask': initial_event_mask,
      'out_bytes': bytearray(b''),
      'in_bytes': bytearray(b''),
      'socket': sock,
      'address': address,
      'port': False,
      'classes': classes
    }

  def register_class_callback(self, event, cl, cb):
    self.class_callbacks[event][cl] = cb

  def do_class_callback_for_event(self, event, fd, socket_details):
    #  Send out callbacks to anything that subscribed to this event
    for c in socket_details['classes']:
      if c in self.class_callbacks[event]:
        self.class_callbacks[event][c](fd, socket_details)
      else:
        #print("Error:  No registered callback for class " + str(c) + " on event " + str(event))
        pass

  def add_to_write_buffer(self, fd, by):
    if fd in self.socket_map:
      socket_details = self.socket_map[fd]
      socket_details['out_bytes'] += by
      socket_details['event_mask'] |= self.WRITE_FLAGS
      self.poller.modify(fd, socket_details['event_mask'])
    else:
      print("fd " + str(fd) + " not known in add_to_write_buffer.")

  def try_remove_message(self, fd):
    MIN_MESSAGE_BYTES = 8 #  size, plus is_binary flag.
    if fd in self.socket_map:
      socket_details = self.socket_map[fd]
      if (len(socket_details['in_bytes'])) >= MIN_MESSAGE_BYTES:
        json_size, binary_size = struct.unpack("II", socket_details['in_bytes'][0:MIN_MESSAGE_BYTES])
        rest = socket_details['in_bytes'][MIN_MESSAGE_BYTES:]
        if (len(rest) >= (json_size + binary_size)):
          json_bytes = rest[0:json_size]
          binary_bytes = rest[json_size:(json_size + binary_size)]
          socket_details['in_bytes'] = socket_details['in_bytes'][(MIN_MESSAGE_BYTES + (json_size + binary_size)):]
          return SloMoMessage(json_bytes, binary_bytes)
      else:
        #  Not enough bytes to even read the size header.
        return None
    else:
      print("fd " + str(fd) + " not known in try_remove_message.")
      return None
    
  def remove_from_read_buffer(self, fd):
    if fd in self.socket_map:
      socket_details = self.socket_map[fd]
      tmp = socket_details['in_bytes']
      socket_details['in_bytes'] = socket_details['in_bytes'][0:0]
      return tmp
    else:
      print("fd " + str(fd) + " not known in remove_from_read_buffer.")
      return bytearray(b'')

  def on_generic_exception(self, fd):
    if fd in self.socket_map:
      socket_details = self.socket_map[fd]
      print("Closing socket " + str(fd) + " due to exception event.")
      if fd:
        if socket_details['socket']:  #  Pure file descriptors don't have sockets.
          socket_details['socket'].close()
        self.do_close(fd, socket_details)
    else:
      print("Exception on unknown fd " + str(fd) + ".")

  def on_generic_write(self, fd):
    if fd in self.socket_map:
      socket_details = self.socket_map[fd]
      if len(socket_details['out_bytes']) == 0:
        socket_details['event_mask'] &= ~self.WRITE_FLAGS
        self.poller.modify(fd, socket_details['event_mask'])
      else:
        if socket_details['is_socket']:  # for file descriptors.
          try:
            send_return = socket_details['socket'].send(socket_details['out_bytes'])
            socket_details['out_bytes'] = socket_details['out_bytes'][send_return:] #  Remove from start of buffer.
          except Exception as e:
            print("Closing socket " + str(fd) + " due to send fail.")
            if fd:
              if socket_details['socket']:  #  Pure file descriptors don't have sockets.
                socket_details['socket'].close()
              self.do_close(fd, socket_details)
        else:
          assert(False) #  TODO Not implemented.
    else:
      print("Write event on unknown fd " + str(fd) + ".")

  def on_generic_read(self, fd):
    if fd in self.socket_map:
      socket_details = self.socket_map[fd]
      if not socket_details['is_listen_socket']:  #  Listen sockets don't have data waiting to recv.
        recv_return = bytearray(b"")
        if socket_details['is_socket']:  # for file descriptors.
          try:
            recv_return = socket_details['socket'].recv(self.recv_size)
          except Exception as e:
            print("e from recv was " + str(e))
        else:
            recv_return = bytearray(os.read(fd, self.recv_size))
        if len(recv_return) == 0:
          print("Closing socket " + str(fd) + " due to 0 byte read.")
          if fd:
            if socket_details['socket']:  #  Pure file descriptors don't have sockets.
              socket_details['socket'].close()
            self.do_close(fd, socket_details)
        else:
          socket_details['in_bytes'].extend(recv_return)
    else:
      print("Write event on unknown fd " + str(fd) + ".")

  def do_close(self, fd, socket_details):
    if fd in self.socket_map:
      self.poller.unregister(fd)
      del self.socket_map[fd]
      self.do_class_callback_for_event('close', fd, socket_details)

  def run(self, poll_timeout):
    if self.debug:
      print("Before poller.poll")
    try:
      events = self.poller.poll(poll_timeout)
      for fd, flag in events:
        socket_details = self.socket_map[fd]
        if flag & (select.POLLIN | select.POLLPRI | select.POLLHUP):
          if self.debug:
            print("read event on fd " + str(fd))
          self.on_generic_read(fd)
          self.do_class_callback_for_event('read', fd, socket_details)
        if flag & (select.POLLOUT):
          if self.debug:
            print("write event on fd " + str(fd))
          self.on_generic_write(fd)
          self.do_class_callback_for_event('write', fd, socket_details)
        if flag & (select.POLLERR):
          if self.debug:
            print("POLLERR event on fd " + str(fd))
          self.on_generic_exception(fd)
          self.do_class_callback_for_event('exception', fd, socket_details)
    except Exception as e:
      print("Caught exception in poll or processing flags: " + str(e))
      traceback.print_exc()
    if self.debug:
      print("After poller.poll")
