#!/usr/bin/env python

import rospy
import numpy as np
import random
import sys
import time
from std_msgs.msg import String, ColorRGBA
from geometry_msgs.msg import Twist
from geometry_msgs.msg import Vector3
from turtlesim.srv import Spawn, SetPen, Kill
from turtlesim.msg import Color, Pose
from sphero_ball_sim.srv import *

x = 0
y = 0
theta = 0

t_0 = 0 # to hold starting time of dance
t_dance = 20 # length of dance in seconds
dance_state = -1
mode = -1 # 0 = waiting to dance, 1 = navigating to a partner, 2 = leading partner to dance, 3 = dancing with partner

# turtle position callback
def pose_callback(data):
	global x
	global y
	global theta
	x = data.x
	y = data.y
	theta = float(np.mod(data.theta,2*np.pi)) # bring angle value to within +2*pi
	#print(data)

# used to begin and end the dance
def music_callback(data):

	global dance_state
	if data.data == 'begin':
		dance_state = 0
		print "Let the dance begin!"
	else:
		dance_state = 99999
		print "The dance has ended"

def add_to_mode_counter(i):

	rospy.set_param('mode_checker_'+str(i),1)

def wait_for_next_mode():

	global mode
	rsum = 0
	for i in range(1,rospy.get_param('total_robot_n')+1):
		rsum = rsum + rospy.get_param('mode_checker_'+str(i))

	while rsum < rospy.get_param('total_robot_n') and rospy.get_param('mode') <= mode :
		time.sleep(1)

	mode = mode + 1
	rospy.set_param('mode',mode)
	for i in range(1,rospy.get_param('total_robot_n')+1):
		rospy.set_param('mode_checker_'+str(i),0)

# used for setup - no social nav involved
def go_to(robot_name,pose_x,pose_y,angle):

	global x
	global y
	global theta

	pub = rospy.Publisher(robot_name+'/cmd_vel', Twist, queue_size=10)
	rate = rospy.Rate(750) #hz

	goal_pose = np.array([pose_x,pose_y])
	current_pose = np.array([x,y])

	direction = goal_pose-current_pose
	goal_angle = np.mod(np.arctan2(direction[1],direction[0]),2*np.pi)
	i = np.sign(goal_angle-theta)
	if abs(goal_angle-theta) > np.pi:
		i = -i
	ang = Vector3(0,0,2*i)
	lin = Vector3(0,0,0)
	while abs(goal_angle-theta)>.01 and np.linalg.norm(direction) != 0:
		stumble = Twist(lin,ang)
		pub.publish(stumble)
		rate.sleep()
	ang = Vector3(0,0,0)
	lin = Vector3(7,0,0)
	while np.linalg.norm(goal_pose-current_pose)>.1 and np.linalg.norm(direction) != 0:
		current_pose = np.array([x,y])
		stumble = Twist(lin,ang)
		pub.publish(stumble)
		rate.sleep()
	goal_angle = float(np.mod(angle,2*np.pi))
	i = np.sign(goal_angle-theta)
	if abs(goal_angle-theta) > np.pi:
		i = -i
	ang = Vector3(0,0,2*i)
	lin = Vector3(0,0,0)
	while abs(theta-goal_angle)>.1:
		stumble = Twist(lin,ang)
		pub.publish(stumble)
		rate.sleep()
	ang = Vector3(0,0,0)
	lin = Vector3(0,0,0)
	stumble = Twist(lin,ang)
	pub.publish(stumble)
	rate.sleep()

def navigate_toward(goal,robot_name,follower_name):
	global x
	global y
	global theta
	pub_vel = rospy.Publisher(robot_name+'/cmd_vel', Twist, queue_size=10)
	rospy.wait_for_service('social_force')
	try:
		social_force = rospy.ServiceProxy('social_force', SocialForce)
		resp2 = social_force(robot_name,goal[0],goal[1],follower_name)
	except rospy.ServiceException, e:
		print "Service call failed: %s"%e

	net_force = np.array([resp2.x,resp2.y])
	force_angle = np.arctan2(net_force[1],net_force[0])
	#print(turtle_name+": Ok! My force angle is "+str(force_angle))

	force_angle = np.mod(force_angle,2*np.pi) # bring angle value to within +2*pi
	angle_difference = np.mod(force_angle - theta,2*np.pi)
	distance_to_goal = np.linalg.norm(goal-np.array([x,y]))

	speed_lin = 2
	speed_ang = speed_lin/2

	# if force angle points in front of robot, turn and move forward at the same time
	if angle_difference < np.pi/2 :
		if angle_difference < .1:
			r_dot = speed_lin
			theta_dot = 0
		else:
			r_dot = speed_lin
			theta_dot = speed_ang
	elif angle_difference > 3*np.pi/2: 
		if angle_difference > 2*np.pi-.1:
			r_dot = speed_lin
			theta_dot = 0
		else:
			r_dot = speed_lin
			theta_dot = -speed_ang
	# otherwise, either back up if goal is close, or spin and then move toward goal
	else:
		i = 1
		if abs(angle_difference) < np.pi:
			i = -1
		if distance_to_goal < 1.2:
			if abs(angle_difference - np.pi) < .1:
				r_dot = -speed_lin
				theta_dot = 0
			else:
				r_dot = -speed_lin
				theta_dot = i*speed_ang
		else:
			r_dot = 0
			theta_dot = -5*i
			lin = Vector3(r_dot,0,0)
			ang = Vector3(0,0,theta_dot)
			while abs(angle_difference)>.05:
				#print(turtle_name+": Ok! My angle error is "+str(angle_difference)+", so I am spinning!")
				angle_difference = force_angle-theta
				stumble = Twist(lin,ang)
				pub_vel.publish(stumble)
			r_dot = speed_lin
			theta_dot = 0
	return (r_dot,theta_dot)


# main driving function for leader
def driver(robot_name,robot_number):

	global mode
	global x
	global y
	global theta
	global dance_state
	global t_0
	global t_dance

	rospy.init_node(robot_name+'_driver', anonymous=True)
	rate = rospy.Rate(750) # hz

	rospy.Subscriber('music', String, music_callback)

	rospy.Subscriber(robot_name+'/pose',Pose,pose_callback)
	p_x = 2*np.mod(robot_number,5)+5
	p_y = 13
	th = -np.pi/2

	while x==0: # wait for published messages to start being read
		time.sleep(1)

	go_to(robot_name,p_x,p_y,th)

	print(robot_name+': ready to go find a dance partner!')
	pub_vel = rospy.Publisher(robot_name+'/cmd_vel', Twist, queue_size=10)
	add_to_mode_counter(int(robot_name.replace('sphero','')))
	wait_for_next_mode()
	#print(robot_name+": Time for the next mode: "+str(mode))

	while not rospy.is_shutdown():

		t = time.time() # current time in seconds
		
		if mode == 0:

			r_dot = 0
			theta_dot = 0

			# stall until you build up the courage to ask someone to dance
			# randomly decide when this leader will go find a partner
			a = np.random.randint(0,8000)
			if a == 7:
				mode = 1
				print(robot_name+": Okay, I'm feeling brave!")

		# go ask a follower to dance
		elif mode == 1:

			follower_number=int(robot_name.replace('sphero',""))
			follower_name = 'sphero' + str(follower_number+1)
			pub_chat = rospy.Publisher(follower_name+'/chatter', String, queue_size=10)

			rospy.wait_for_service('robot_locator')
			try:
				robot_locator = rospy.ServiceProxy('robot_locator', RobotLocator)
				resp1 = robot_locator(follower_name)
			except rospy.ServiceException, e:
				print "Service call failed: %s"%e

			their_pose = np.array([resp1.x,resp1.y])
			goal = their_pose + 2.5*np.array([np.cos(resp1.theta),np.sin(resp1.theta)])

			if np.linalg.norm(goal-np.array([x,y]))<.3:
				print(robot_name+": Would you like to dance, "+follower_name+"?")
				dance_proposal = String(robot_name)
				pub_chat.publish(dance_proposal)
				r_dot = 0
				theta_dot = 0
				mode = mode+1
				#print(robot_name+": Time for the next mode: "+str(mode))
				rate = rospy.Rate(.5) #hz
			else:
				# navigate to partner using force model
				(r_dot,theta_dot) = navigate_toward(goal,robot_name,follower_name)

		elif mode == 2:
			rate = rospy.Rate(750) #hz

			# navigate to dance floor using force model
			goal = np.array([3*int(robot_name.replace('sphero','')),8])

			if np.linalg.norm(goal-np.array([x,y]))<.3:
				go_to(robot_name,x,y,-np.pi/2)
				add_to_mode_counter(int(robot_name.replace('sphero','')))
				print(robot_name+": Okay, ready to start the dance!")
				wait_for_next_mode()
				#print(robot_name+": Time for the next mode: "+str(mode))
				lin = Vector3(0,0,0)
				ang = Vector3(0,0,0)
				glide = Twist(lin,ang)
				pub_vel.publish(glide)
				t_0 = time.time()
			else:
				(r_dot,theta_dot) = navigate_toward(goal,robot_name,follower_name)

		elif mode == 3:

			# dance with partner and avoid others
			if dance_state == -1:
				r_dot = 0
				theta_dot = 0
			else:
				if dance_state == 0:

					try:
						robot_locator = rospy.ServiceProxy('robot_locator', RobotLocator)
						resp1 = robot_locator(follower_name)
					except rospy.ServiceException, e:
						print "Service call failed: %s"%e
					their_pose = np.array([resp1.x,resp1.y])

					# make sure to face your partner
					direction = their_pose-np.array([x,y])
					th = np.mod(np.arctan2(direction[1],direction[0]),2*np.pi)
					go_to(robot_name,x,y,th)

					rate = rospy.Rate(.5) # hz
					goal = np.array([x,y]) - 0.5*np.array([np.cos(theta),np.sin(theta)])
					(r_dot,theta_dot) = navigate_toward(goal,robot_name,follower_name)
				elif dance_state == 1:
					goal = np.array([x,y]) + 0.5*np.array([np.cos(theta),np.sin(theta)])
					(r_dot,theta_dot) = navigate_toward(goal,robot_name,follower_name)
				elif dance_state >= 2 and dance_state < 100:
					rate = rospy.Rate(2) # hz
					(r_dot,theta_dot) = (-.5*1.5,-.5)
				else:
					rate = rospy.Rate(750) # hz
					print(robot_name+": Thank you for a lovely dance, "+follower_name+".")
					dance_end = String('bow')
					pub_chat.publish(dance_end)
					mode = 4

				#(r_dot,theta_dot) = navigate_toward(goal,robot_name,follower_name)
				dance_state = np.mod(dance_state + 1,12)

		else: 
			goal = [x,13]
			if np.linalg.norm(goal-np.array([x,y])) < .3:
				(r_dot,theta_dot) = (0,0)
			else:
				(r_dot,theta_dot) = navigate_toward(goal,robot_name,follower_name)

		lin = Vector3(r_dot,0,0)
		ang = Vector3(0,0,theta_dot)

		glide = Twist(lin,ang)
		pub_vel.publish(glide)
		rate.sleep()

if __name__ == '__main__':

	baby_number = int(rospy.myargv(argv=sys.argv)[1])
	baby_name = 'sphero'+str(baby_number)
	if baby_number <= rospy.get_param('total_robot_n'):

		while rospy.get_param("setup_complete") == False:
			time.sleep(1)

		try:
			driver('sphero'+str(baby_number),baby_number)
			rospy.spin() # same here. Does it matter if it's in driver() or not? - ilse
		except rospy.ROSInterruptException:
			pass


