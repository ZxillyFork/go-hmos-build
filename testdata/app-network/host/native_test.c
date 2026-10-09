// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

// Host-only tests. GNU ld --wrap injects failures only into this executable,
// never into the target c-shared library.
#define _GNU_SOURCE
#include "native.h"
#include <assert.h>
#include <arpa/inet.h>
#include <errno.h>
#include <ifaddrs.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static int reject_bind, reject_broadcast, reject_interfaces, timeout_poll;
static int fake_interfaces, malformed_netmask;
static struct ifaddrs *synthetic_interfaces;

int __real_bind(int, const struct sockaddr *, socklen_t);
int __real_setsockopt(int, int, int, const void *, socklen_t);
int __real_getifaddrs(struct ifaddrs **);
void __real_freeifaddrs(struct ifaddrs *);
int __real_poll(struct pollfd *, nfds_t, int);

int __wrap_bind(int fd, const struct sockaddr *address, socklen_t size)
{
	if (reject_bind) { errno = EPERM; return -1; }
	return __real_bind(fd, address, size);
}

int __wrap_setsockopt(int fd, int level, int option, const void *value, socklen_t size)
{
	if (reject_broadcast && level == SOL_SOCKET && option == SO_BROADCAST) {
		errno = EPERM;
		return -1;
	}
	return __real_setsockopt(fd, level, option, value, size);
}

int __wrap_getifaddrs(struct ifaddrs **list)
{
	if (reject_interfaces) { errno = EACCES; return -1; }
	if (fake_interfaces) {
		struct ifaddrs *v4 = calloc(1, sizeof(*v4));
		struct ifaddrs *v6 = calloc(1, sizeof(*v6));
		assert(v4 && v6);
		v4->ifa_name = strdup("lo");
		v6->ifa_name = strdup("lo");
		v4->ifa_addr = calloc(1, sizeof(struct sockaddr_in));
		v4->ifa_netmask = calloc(1, sizeof(struct sockaddr_in));
		v6->ifa_addr = calloc(1, sizeof(struct sockaddr_in6));
		v6->ifa_netmask = calloc(1, sizeof(struct sockaddr_in6));
		assert(v4->ifa_name && v6->ifa_name && v4->ifa_addr && v4->ifa_netmask && v6->ifa_addr && v6->ifa_netmask);
		v4->ifa_addr->sa_family = AF_INET;
		v4->ifa_netmask->sa_family = AF_INET;
		v6->ifa_addr->sa_family = AF_INET6;
		v6->ifa_netmask->sa_family = AF_INET6;
		assert(inet_pton(AF_INET, "127.0.0.1", &((struct sockaddr_in *)v4->ifa_addr)->sin_addr) == 1);
		assert(inet_pton(AF_INET, malformed_netmask ? "255.0.255.0" : "255.0.0.0", &((struct sockaddr_in *)v4->ifa_netmask)->sin_addr) == 1);
		assert(inet_pton(AF_INET6, "::1", &((struct sockaddr_in6 *)v6->ifa_addr)->sin6_addr) == 1);
		memset(&((struct sockaddr_in6 *)v6->ifa_netmask)->sin6_addr, 255, sizeof(struct in6_addr));
		v4->ifa_next = v6;
		synthetic_interfaces = *list = v4;
		return 0;
	}
	return __real_getifaddrs(list);
}

void __wrap_freeifaddrs(struct ifaddrs *list)
{
	if (list != synthetic_interfaces || !list) {
		__real_freeifaddrs(list);
		return;
	}
	while (list) {
		struct ifaddrs *next = list->ifa_next;
		free(list->ifa_name);
		free(list->ifa_addr);
		free(list->ifa_netmask);
		free(list);
		list = next;
	}
	synthetic_interfaces = NULL;
}

int __wrap_poll(struct pollfd *fds, nfds_t count, int timeout)
{
	if (timeout_poll) return 0;
	return __real_poll(fds, count, timeout);
}

static void check(int operation, int expected_errno)
{
	struct app_network_result *r = app_network_run(operation, 3000);
	assert(r);
	assert(r->pid == getpid());
	assert(r->uid == (int)getuid());
	assert(r->gid == (int)getgid());
	assert(r->socket_flags == (SOCK_NONBLOCK | SOCK_CLOEXEC));
	if (r->passed != (expected_errno == 0) || r->error_number != expected_errno) {
		fprintf(stderr, "operation=%d pass=%d errno=%d stage=%s error=%s; want errno=%d\n",
			operation, r->passed, r->error_number, r->stage, r->error_text, expected_errno);
		assert(0);
	}
	if (operation == APP_GETIFADDRS && !expected_errno) {
		assert(r->interface_count > 0);
		int addresses = 0;
		for (size_t i = 0; i < r->interface_count; i++) {
			assert(r->interfaces[i].name[0]);
			if (r->interfaces[i].address[0]) {
				assert(r->interfaces[i].prefix_length >= 0);
				addresses++;
			}
		}
		assert(addresses > 0);
	}
	app_network_result_free(r);
}

int main(int argc, char **argv)
{
	if (argc == 2 && strcmp(argv[1], "--interfaces") == 0) {
		struct app_network_result *interfaces = app_network_run(APP_GETIFADDRS, 3000);
		assert(interfaces);
		if (!interfaces->passed && (interfaces->error_number == EPERM || interfaces->error_number == EACCES)) {
			printf("SKIP: host environment denies getifaddrs: errno=%d %s\n", interfaces->error_number, interfaces->error_text);
			app_network_result_free(interfaces);
			return 77;
		}
		app_network_result_free(interfaces);
		check(APP_GETIFADDRS, 0);
		puts("PASS: host-only getifaddrs interface/address enumeration; target execution NOT PERFORMED");
		return 0;
	}
	for (int round = 0; round < 8; round++)
		for (int op = APP_RAW_TCP_BIND; op < APP_GETIFADDRS; op++)
			check(op, 0);
	reject_bind = 1;
	check(APP_RAW_TCP_BIND, EPERM);
	check(APP_RAW_UDP_BIND, EPERM);
	check(APP_TCP_ROUNDTRIP, EPERM);
	check(APP_UDP_ROUNDTRIP, EPERM);
	// A failed bind must not prevent an independent setsockopt operation.
	check(APP_RAW_UDP_BROADCAST, 0);
	reject_bind = 0;
	reject_broadcast = 1;
	check(APP_RAW_UDP_BROADCAST, EPERM);
	check(APP_RAW_UDP_BIND, 0);
	reject_broadcast = 0;
	reject_interfaces = 1;
	check(APP_GETIFADDRS, EACCES);
	reject_interfaces = 0;
	fake_interfaces = 1;
	check(APP_GETIFADDRS, 0);
	struct app_network_result *synthetic = app_network_run(APP_GETIFADDRS, 3000);
	assert(synthetic && synthetic->passed && synthetic->interface_count == 2);
	assert(strcmp(synthetic->interfaces[0].address, "127.0.0.1") == 0 && synthetic->interfaces[0].prefix_length == 8);
	assert(strcmp(synthetic->interfaces[1].address, "::1") == 0 && synthetic->interfaces[1].prefix_length == 128);
	app_network_result_free(synthetic);
	malformed_netmask = 1;
	check(APP_GETIFADDRS, EINVAL);
	malformed_netmask = 0;
	fake_interfaces = 0;
	timeout_poll = 1;
	check(APP_TCP_ROUNDTRIP, ETIMEDOUT);
	check(APP_UDP_ROUNDTRIP, ETIMEDOUT);
	timeout_poll = 0;
	check(-1, EINVAL);
	struct app_network_result *r = app_network_run(APP_RAW_TCP_BIND, 0);
	assert(r && !r->passed && r->error_number == EINVAL);
	app_network_result_free(r);
	app_network_result_free(NULL);
	check(APP_TCP_ROUNDTRIP, 0);
	check(APP_UDP_ROUNDTRIP, 0);
	puts("PASS: host-only native network fixture and injected failure/deadline tests; target execution NOT PERFORMED");
	return 0;
}
