// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

#ifndef __OHOS__
#error expected OpenHarmony SDK compiler
#endif

#include <ifaddrs.h>
#include <pthread.h>
#include <stdio.h>

static void *
run(void *argument)
{
	int *value = argument;
	*value = 42;
	return argument;
}

int
main(void)
{
	pthread_t thread;
	int value = 0;
	void *result = 0;
	if (pthread_create(&thread, 0, run, &value) != 0)
		return 1;
	if (pthread_join(thread, &result) != 0)
		return 2;
	if (result != &value || value != 42)
		return 3;
	puts("PASS: OpenHarmony native C ABI");
	return 0;
}
