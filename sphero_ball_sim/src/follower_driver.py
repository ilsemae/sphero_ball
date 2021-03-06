#!/usr/bin/env python

import rospy
import numpy as np
import time
import sys
from std_msgs.msg import String, ColorRGBA
from geometry_msgs.msg import Twist
from geometry_msgs.msg import Vector3
from turtlesim.srv import Kill, Spawn, SetPen
from turtlesim.msg import Pose
from sphero_ball_sim.srv import *


x = 0
y = 0
theta = 0

dance_begun = False

mode = -1 # 0 = waiting to be asked, 1 = waiting to be asked, 2 = following leader to dancefloor, 3 = dancing with partner

# for leaders to ask followers to dance
def chatter_callback(data):
	global mode
	if data.data == "bow":
		print "Thank you as well!"
		mode = 4
	else:
		print "That would be lovely, "+data.data+"!"

# turtle position callback
def pose_callback(data):
	global x
	global y
	global theta
	x = data.x
	y = data.y
	theta = float(np.mod(data.theta,2*np.pi)) # bring angle value to within +2*pi

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
	# if you are not at your goal x,y, spin until you are facing your goal:
	while abs(goal_angle-theta)>.01 and np.linalg.norm(direction) > 0.1:
		#print "spinning to face goal position"
		stumble = Twist(lin,ang)
		pub.publish(stumble)
		rate.sleep()
	ang = Vector3(0,0,0)
	lin = Vector3(7,0,0)
	# move toward your goal
	while np.linalg.norm(goal_pose-current_pose) > 0.1 and np.linalg.norm(direction) > 0.1:
		#print "moving toward goal position"
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
	# spin until you reach your given angle
	while abs(theta-goal_angle)>.1:
		#print "now spinning to desired theta"
		stumble = Twist(lin,ang)
		pub.publish(stumble)
		rate.sleep()
	ang = Vector3(0,0,0)
	lin = Vector3(0,0,0)
	stumble = Twist(lin,ang)
	pub.publish(stumble)
	rate.sleep()

def navigate_toward(goal,robot_name,leader_name):
	global x
	global y
	global theta
	pub_vel = rospy.Publisher(robot_name+'/cmd_vel', Twist, queue_size=10)
	rospy.wait_for_service('social_force')
	try:
		social_force = rospy.ServiceProxy('social_force', SocialForce)
		resp2 = social_force(robot_name,goal[0],goal[1],leader_name)
	except rospy.ServiceException, e:
		print "Service call failed: %s"%e

	net_force = np.array([resp2.x,resp2.y])
	force_angle = np.arctan2(net_force[1],net_force[0])
	#print(turtle_name+": Ok! My force angle is "+str(force_angle))

	force_angle = np.mod(force_angle,2*np.pi) # bring angle value to within +2*pi
	angle_difference = np.mod(force_angle - theta,2*np.pi)
	distance_to_goal = np.linalg.norm(goal-np.array([x,y]))

	if distance_to_goal < .1 :
		return (0,0)

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

def smiler(robot_name,smile,goal,leader_name):
	global x
	global y
	global mode
	(r_dot,theta_dot) = (0,0)
	if smile != 0:
		(r_dot,theta_dot) = navigate_toward(goal,robot_name,leader_name)
	return (r_dot,theta_dot)

#		th = np.mod(np.arctan2(direction[1],direction[0]),2*np.pi) - (5-smile)*np.pi/10
#		go_to(robot_name,x,y,th)

# main driving function for followers
def follow(robot_name,robot_number):

	global mode
	global x
	global y
	global theta
	global smile

	rospy.init_node(robot_name+'_driver', anonymous=True)
	rate = rospy.Rate(750) # hz
	rospy.Subscriber(robot_name+'/chatter',String,chatter_callback)

	rospy.Subscriber(robot_name+'/pose',Pose,pose_callback)
	p_x = robot_number/1.5+7
	p_y = 2
	th = np.pi/2

	while x==0: # wait for published messages to start being read
		time.sleep(1)

	go_to(robot_name,p_x,p_y,th)

	print(robot_name+': ready to be asked to dance!')
	pub_vel = rospy.Publisher(robot_name+'/cmd_vel', Twist, queue_size=10)
	add_to_mode_counter(int(robot_name.replace('sphero','')))
	wait_for_next_mode()
	#print(robot_name+": Time for the next mode: "+str(mode))

	while not rospy.is_shutdown():

		if mode == 0:
			# wait
			r_dot = 0
			theta_dot = 0
			mode = 1

		elif mode == 1:
			# if a leader gets close, turn toward or away from them
			leader_name = 'sphero'+str(int(robot_name.replace('sphero',''))-1)
			rospy.wait_for_service('robot_locator')
			try:
				robot_locator = rospy.ServiceProxy('robot_locator', RobotLocator)
				resp1 = robot_locator(leader_name)
			except rospy.ServiceException, e:
				print "Service call failed: %s"%e
			their_pose = np.array([resp1.x,resp1.y])
			direction = their_pose-np.array([x,y])
			if np.linalg.norm(direction) < 3:
				print p_x,p_y
				print x, y
				(r_dot,theta_dot) = smiler(robot_name,smile,np.array([x,y])+np.sign(smile)*direction/np.linalg.norm(direction),leader_name)
				lin = Vector3(r_dot,0,0)
				ang = Vector3(0,0,theta_dot)
				glide = Twist(lin,ang)
				pub_vel.publish(glide)
				time.sleep(.5)
				lin = Vector3(0,0,0)
				ang = Vector3(0,0,0)
				glide = Twist(lin,ang)
				pub_vel.publish(glide)
				if smile > 0:
					go_to(robot_name,x,y,theta + np.pi/7)
					go_to(robot_name,x,y,theta - np.pi/7)
					go_to(robot_name,x,y,theta + np.pi/7)
					go_to(robot_name,x,y,theta - np.pi/7)
					go_to(robot_name,x,y,theta + np.pi/7)
					time.sleep(1.5)
				elif smile < 0:
					#go_to(robot_name,x,y,theta + np.pi/4)
					time.sleep(3.5)
				else:
					time.sleep(3.5)
				mode = 2

		elif mode == 2:
			# navigate to dance floor using force model
			try:
				robot_locator = rospy.ServiceProxy('robot_locator', RobotLocator)
				resp1 = robot_locator(leader_name)
			except rospy.ServiceException, e:
				print "Service call failed: %s"%e
			their_pose = np.array([resp1.x,resp1.y])
			goal = their_pose + np.array([0,-1.5])
			if np.linalg.norm(goal-np.array([x,y]))<.3:
				go_to(robot_name,x,y,np.pi/2)
				lin = Vector3(0,0,0)
				ang = Vector3(0,0,0)
				glide = Twist(lin,ang)
				pub_vel.publish(glide)
				add_to_mode_counter(int(robot_name.replace('sphero','')))
				wait_for_next_mode()
			else:
				(r_dot,theta_dot) = navigate_toward(goal,robot_name,leader_name)

		elif mode == 3:
			global dance_begun
			# dance with partner and avoid others
			try:
				robot_locator = rospy.ServiceProxy('robot_locator', RobotLocator)
				resp1 = robot_locator(leader_name)
			except rospy.ServiceException, e:
				print "Service call failed: %s"%e
			their_pose = np.array([resp1.x,resp1.y])
			their_angle = resp1.theta
			# make sure to face your partner
			direction = their_pose-np.array([x,y])
			th = np.mod(np.arctan2(direction[1],direction[0]),2*np.pi)
			if np.linalg.norm(th-theta) > 0.2:
				go_to(robot_name,x,y,th)
			# stay a certain distance in front of your partner
			goal = their_pose - 1.5*direction/np.linalg.norm(direction)
			if np.linalg.norm(goal-np.array([x,y])) < .3:
				(r_dot,theta_dot) = (0,0)
				if dance_begun == False:
					if smile > 0:
						go_to(robot_name,x,y,theta + np.pi/7)
						go_to(robot_name,x,y,theta - np.pi/7)
			else:
				dance_begun = True
				(r_dot,theta_dot) = navigate_toward(goal,robot_name,leader_name)

		else:
			goal = [x,1]
			if np.linalg.norm(goal-np.array([x,y])) < .3:
				(r_dot,theta_dot) = (0,0)
			else:
				(r_dot,theta_dot) = navigate_toward(goal,robot_name,leader_name)

		lin = Vector3(r_dot,0,0)
		ang = Vector3(0,0,theta_dot)

		stumble = Twist(lin,ang)
		pub_vel.publish(stumble)
		rate.sleep()

if __name__ == '__main__':

	baby_number = int(rospy.myargv(argv=sys.argv)[1])
	baby_name = 'sphero'+str(baby_number)
	if baby_number <= rospy.get_param('total_robot_n'):
		# defines how happy a robot is about dancing. All but sphero2 will be neutral (0)
		# sphero2's value will be varied for our experment. -1 = unhappy, 1 = happy
		if baby_name == 'sphero2':
			smile = 0
		else:
			smile = 0


		while rospy.get_param("setup_complete") == False:
			time.sleep(1)

		try:
			follow(baby_name,baby_number)
			rospy.spin() # not sure why I put this here. Perhaps it should go inside follow()
		except rospy.ROSInterruptException:
			pass

	
