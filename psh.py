#!/usr/bin/env python3

def evaluate(thing):
	return eval(thing)

def main():
	while True:
		print(evaluate(input(">> ")))

if __name__ == '__main__':
	main()