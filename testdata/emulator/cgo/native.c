// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

#include <pthread.h>
#include "native.h"

extern int emulatorGoCallback(int seed);

static _Thread_local int tlsValue;

void
emulatorSetTLS(int value)
{
	tlsValue = value;
}

int
emulatorGetTLS(void)
{
	return tlsValue;
}

int
emulatorAdd(int a, int b)
{
	return a + b;
}

struct worker {
	int seed;
	int failed;
};

static void *
runWorker(void *argument)
{
	struct worker *worker = argument;
	tlsValue = worker->seed;
	for (int i = 0; i < 32; i++) {
		int seed = worker->seed + i;
		if (emulatorGoCallback(seed) != seed * 2 + 1 || tlsValue != worker->seed) {
			worker->failed = 1;
			break;
		}
	}
	return 0;
}

int
emulatorPthreads(void)
{
	pthread_t threads[4];
	struct worker workers[4];
	int started = 0;
	int status = 0;
	for (int i = 0; i < 4; i++) {
		workers[i].seed = i + 1;
		workers[i].failed = 0;
		if (pthread_create(&threads[i], 0, runWorker, &workers[i]) != 0) {
			status = 1;
			break;
		}
		started++;
	}
	for (int i = 0; i < started; i++) {
		if (pthread_join(threads[i], 0) != 0) {
			// Returning would let a live worker access this function's stack.
			// Exit the test process immediately rather than risk a false pass.
			__builtin_trap();
		}
		if (workers[i].failed)
			status = 2;
	}
	return status;
}
