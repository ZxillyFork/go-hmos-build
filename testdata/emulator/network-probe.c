// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

// Use the SDK libc APIs directly, without Go, to distinguish guest network
// permission failures from Go's syscall/runtime implementation.
#ifndef __OHOS__
#error expected OpenHarmony SDK compiler
#endif

#include <arpa/inet.h>
#include <errno.h>
#include <ifaddrs.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static int
check_bind(int type, const char *name)
{
	int fd = socket(AF_INET, type, 0);
	if (fd < 0) {
		printf("FAIL: native %s socket: errno=%d (%s)\n", name, errno, strerror(errno));
		return 1;
	}
	struct sockaddr_in address = {0};
	address.sin_family = AF_INET;
	address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
	address.sin_port = 0;
	int result = bind(fd, (struct sockaddr *)&address, sizeof(address));
	int saved_errno = errno;
	close(fd);
	if (result < 0) {
		printf("FAIL: native %s bind: errno=%d (%s)\n", name, saved_errno, strerror(saved_errno));
		return 1;
	}
	printf("PASS: native %s bind\n", name);
	return 0;
}

int
main(void)
{
	int failed = check_bind(SOCK_STREAM, "tcp");
	failed |= check_bind(SOCK_DGRAM, "udp");
	struct ifaddrs *interfaces = 0;
	if (getifaddrs(&interfaces) < 0) {
		printf("FAIL: native getifaddrs: errno=%d (%s)\n", errno, strerror(errno));
		failed = 1;
	} else {
		freeifaddrs(interfaces);
		puts("PASS: native getifaddrs");
	}
	if (!failed)
		puts("PASS: OpenHarmony native network");
	return failed;
}
