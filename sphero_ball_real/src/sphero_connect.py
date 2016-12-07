#!/usr/bin/env python

import rospy
import numpy as np
import time
import sys
from rosgraph_msgs.msg import Log
from subprocess import Popen

class RobotSetup:

	def __init__(self):
		self.n = 1
		rospy.init_node('robot_setup')
		self.bt = 0
		rospy.Subscriber('rosout', Log, self.set_bt_state)
		self.connect_to_spheros()

	def connect_to_spheros(self):
		""" Loops until a Sphero is connected. """
		i = 0
		while i < self.n:
			self.bt = 0
			# Give the Sphero a unique name.
			name = 'sphero'+str(sys.argv[1])
			# Start a new sphero.py process to begin connecting.
			p = Popen(['rosrun', 'sphero_node', 'sphero.py', '__ns:=' + name])
			# Spin our wheels while connecting.
			while not self.bt:
				if p.poll():
					break
			if not p.returncode:
				if self.bt == 1:
					i += 1
				elif self.bt == -1:
					continue
			else:
				break

	def set_bt_state(self, log):
		""" Sets our Bluetooth variable based on the connection success. """
		if "Connect to Sphero with address" in log.msg:
			self.bt =  1
		elif "Failed to connect to Sphero." in log.msg:
			self.bt = -1


if __name__ == '__main__':

	RobotSetup()		