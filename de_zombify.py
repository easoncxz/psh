
import os
import signal
import readline
import subprocess

def main():
	pid = os.fork()
	if not pid:
		os.execvp('sleep', ['sleep', '1'])
	else:
		input()
		os.system('ps -p {} -o pid,state,comm='.format(pid))
		input()
		os.waitpid(pid, 0)
		os.system('ps -p {} -o pid,state,comm='.format(pid))
		input()

if __name__ == '__main__':
	main()