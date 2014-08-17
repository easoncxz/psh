
def obs():
	import os
	pid = os.fork()
	if not pid:
		# child
		os.execvp('wget', ['wget', 'https://farm4.staticflickr.com/3705/13922346983_0da89025d7_o_d.jpg'])
	else:
		# parent
		os.waitpid(pid, 0)
		print("{} is finally done.".format(pid))

def main():
	import os
	pipein, pipeout = os.pipe()
	child_pid = os.fork()
	if not child_pid:
		# child
		os.dup2(pipeout, 1)
		os.close(pipeout)
		os.execvp('ls', ['ls', '-l'])
	else:
		# parent
		# os.waitpid(child_pid, 0)
		os.dup2(pipein, 0)
		os.close(pipein)
		os.execvp('wc', ['wc'])

if __name__ == '__main__':
	main()