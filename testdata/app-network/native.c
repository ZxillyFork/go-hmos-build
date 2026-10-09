// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

#define _GNU_SOURCE
#include "native.h"

#include <arpa/inet.h>
#include <errno.h>
#include <ifaddrs.h>
#include <limits.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static const char payload[] = "go-hmos-app-network\0native-roundtrip";

static void
fail(struct app_network_result *r, const char *stage, int error_number)
{
	r->passed = 0;
	r->error_number = error_number;
	snprintf(r->stage, sizeof(r->stage), "%s", stage);
	snprintf(r->error_text, sizeof(r->error_text), "%s", strerror(error_number));
}

static int64_t
now_ms(void)
{
	struct timespec ts;
	if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
		return -1;
	return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static int
wait_fd(int fd, short events, int64_t deadline)
{
	for (;;) {
		int64_t now = now_ms();
		if (now < 0)
			return -1;
		if (now >= deadline) {
			errno = ETIMEDOUT;
			return -1;
		}
		int64_t remaining = deadline - now;
		int timeout = remaining > INT_MAX ? INT_MAX : (int)remaining;
		struct pollfd p = {.fd = fd, .events = events};
		int status = poll(&p, 1, timeout);
		if (status < 0 && errno == EINTR)
			continue;
		if (status == 0) {
			errno = ETIMEDOUT;
			return -1;
		}
		if (status < 0)
			return -1;
		if (p.revents & POLLNVAL) {
			errno = EBADF;
			return -1;
		}
		// POLLERR/POLLHUP are deliberately returned to the next socket operation
		// so that its real errno, or SO_ERROR after connect, is preserved.
		if (p.revents & (events | POLLERR | POLLHUP))
			return 0;
	}
}

static struct sockaddr_in
loopback(void)
{
	struct sockaddr_in address;
	memset(&address, 0, sizeof(address));
	address.sin_family = AF_INET;
	address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
	return address;
}

static int
new_socket(struct app_network_result *r, int type, const char *stage)
{
	int fd = socket(AF_INET, type | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
	if (fd < 0)
		fail(r, stage, errno);
	return fd;
}

static int
bind_loopback(struct app_network_result *r, int fd, struct sockaddr_in *address,
	const char *stage)
{
	if (bind(fd, (struct sockaddr *)address, sizeof(*address)) != 0) {
		fail(r, stage, errno);
		return -1;
	}
	return 0;
}

static void
raw_bind(struct app_network_result *r, int type)
{
	int fd = new_socket(r, type, "socket");
	if (fd < 0)
		return;
	struct sockaddr_in address = loopback();
	if (bind_loopback(r, fd, &address, "bind(127.0.0.1:0)") == 0)
		r->passed = 1;
	close(fd);
}

static void
raw_broadcast(struct app_network_result *r)
{
	int fd = new_socket(r, SOCK_DGRAM, "socket");
	if (fd < 0)
		return;
	int enabled = 1;
	if (setsockopt(fd, SOL_SOCKET, SO_BROADCAST, &enabled, sizeof(enabled)) != 0)
		fail(r, "setsockopt(SOL_SOCKET,SO_BROADCAST,1)", errno);
	else
		r->passed = 1;
	close(fd);
}

static int
stream_write(int fd, const void *data, size_t size, int64_t deadline)
{
	size_t done = 0;
	while (done < size) {
		if (wait_fd(fd, POLLOUT, deadline) != 0)
			return -1;
		ssize_t n = send(fd, (const char *)data + done, size - done, MSG_NOSIGNAL);
		if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK))
			continue;
		if (n <= 0) {
			if (n == 0)
				errno = EIO;
			return -1;
		}
		done += (size_t)n;
	}
	return 0;
}

static int
stream_read(int fd, void *data, size_t size, int64_t deadline)
{
	size_t done = 0;
	while (done < size) {
		if (wait_fd(fd, POLLIN, deadline) != 0)
			return -1;
		ssize_t n = recv(fd, (char *)data + done, size - done, 0);
		if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK))
			continue;
		if (n <= 0) {
			if (n == 0)
				errno = ECONNRESET;
			return -1;
		}
		done += (size_t)n;
	}
	return 0;
}

static void
tcp_roundtrip(struct app_network_result *r, int64_t deadline)
{
	int listener = -1, client = -1, accepted = -1;
	const char *stage = "socket(listener)";
	struct sockaddr_in address = loopback();
	socklen_t address_len = sizeof(address);
	char received[sizeof(payload)];
	listener = new_socket(r, SOCK_STREAM, stage);
	if (listener < 0)
		goto done;
	if (bind_loopback(r, listener, &address, "bind(listener,127.0.0.1:0)") != 0)
		goto done;
	stage = "listen";
	if (listen(listener, 1) != 0)
		goto failed;
	stage = "getsockname(listener)";
	if (getsockname(listener, (struct sockaddr *)&address, &address_len) != 0)
		goto failed;
	client = new_socket(r, SOCK_STREAM, "socket(client)");
	if (client < 0)
		goto done;
	stage = "connect(client)";
	if (connect(client, (struct sockaddr *)&address, sizeof(address)) != 0) {
		if (errno != EINPROGRESS)
			goto failed;
		stage = "poll(connect)";
		if (wait_fd(client, POLLOUT, deadline) != 0)
			goto failed;
		int pending = 0;
		socklen_t pending_len = sizeof(pending);
		stage = "getsockopt(SO_ERROR)";
		if (getsockopt(client, SOL_SOCKET, SO_ERROR, &pending, &pending_len) != 0)
			goto failed;
		if (pending != 0) {
			errno = pending;
			goto failed;
		}
	}
	stage = "accept4";
	for (;;) {
		if (wait_fd(listener, POLLIN, deadline) != 0)
			goto failed;
		accepted = accept4(listener, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
		if (accepted >= 0)
			break;
		if (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK)
			goto failed;
	}
	stage = "send(client->server)";
	if (stream_write(client, payload, sizeof(payload), deadline) != 0)
		goto failed;
	stage = "recv(server)";
	if (stream_read(accepted, received, sizeof(received), deadline) != 0)
		goto failed;
	stage = "verify(server payload)";
	if (memcmp(received, payload, sizeof(payload)) != 0) {
		errno = EIO;
		goto failed;
	}
	stage = "send(server->client)";
	if (stream_write(accepted, received, sizeof(received), deadline) != 0)
		goto failed;
	stage = "recv(client)";
	if (stream_read(client, received, sizeof(received), deadline) != 0)
		goto failed;
	stage = "verify(client payload)";
	if (memcmp(received, payload, sizeof(payload)) != 0) {
		errno = EIO;
		goto failed;
	}
	r->passed = 1;
	goto done;
failed:
	fail(r, stage, errno);
done:
	if (accepted >= 0) close(accepted);
	if (client >= 0) close(client);
	if (listener >= 0) close(listener);
}

static int
datagram_send(int fd, const struct sockaddr_in *address, int64_t deadline)
{
	for (;;) {
		if (wait_fd(fd, POLLOUT, deadline) != 0)
			return -1;
		ssize_t n = sendto(fd, payload, sizeof(payload), MSG_NOSIGNAL,
			(const struct sockaddr *)address, sizeof(*address));
		if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK))
			continue;
		if (n < 0)
			return -1;
		if (n != sizeof(payload)) {
			errno = EIO;
			return -1;
		}
		return 0;
	}
}

static int
datagram_receive(int fd, struct sockaddr_in *peer, int64_t deadline)
{
	for (;;) {
		if (wait_fd(fd, POLLIN, deadline) != 0)
			return -1;
		socklen_t peer_len = sizeof(*peer);
		char received[sizeof(payload) + 1];
		ssize_t n = recvfrom(fd, received, sizeof(received), 0,
			(struct sockaddr *)peer, &peer_len);
		if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK))
			continue;
		if (n < 0)
			return -1;
		if (n != sizeof(payload) || memcmp(received, payload, sizeof(payload)) != 0) {
			errno = EIO;
			return -1;
		}
		return 0;
	}
}

static void
udp_roundtrip(struct app_network_result *r, int64_t deadline)
{
	int server = -1, client = -1;
	const char *stage;
	struct sockaddr_in address = loopback(), client_address = loopback(), peer;
	socklen_t address_len = sizeof(address);
	server = new_socket(r, SOCK_DGRAM, "socket(server)");
	if (server < 0)
		goto done;
	if (bind_loopback(r, server, &address, "bind(server,127.0.0.1:0)") != 0)
		goto done;
	stage = "getsockname(server)";
	if (getsockname(server, (struct sockaddr *)&address, &address_len) != 0)
		goto failed;
	client = new_socket(r, SOCK_DGRAM, "socket(client)");
	if (client < 0)
		goto done;
	if (bind_loopback(r, client, &client_address, "bind(client,127.0.0.1:0)") != 0)
		goto done;
	stage = "sendto(client->server)";
	if (datagram_send(client, &address, deadline) != 0)
		goto failed;
	stage = "recvfrom(server)/verify";
	if (datagram_receive(server, &peer, deadline) != 0)
		goto failed;
	stage = "sendto(server->client)";
	if (datagram_send(server, &peer, deadline) != 0)
		goto failed;
	stage = "recvfrom(client)/verify";
	if (datagram_receive(client, &peer, deadline) != 0)
		goto failed;
	r->passed = 1;
	goto done;
failed:
	fail(r, stage, errno);
done:
	if (client >= 0) close(client);
	if (server >= 0) close(server);
}

static int
prefix_length(const unsigned char *mask, size_t size)
{
	int bits = 0, zero_seen = 0;
	for (size_t i = 0; i < size; i++) {
		for (int bit = 7; bit >= 0; bit--) {
			if ((mask[i] >> bit) & 1) {
				if (zero_seen)
					return -1;
				bits++;
			} else {
				zero_seen = 1;
			}
		}
	}
	return bits;
}

static void
interfaces(struct app_network_result *r)
{
	struct ifaddrs *list = NULL;
	if (getifaddrs(&list) != 0) {
		fail(r, "getifaddrs", errno);
		return;
	}
	size_t count = 0;
	for (struct ifaddrs *item = list; item; item = item->ifa_next)
		count++;
	if (count > SIZE_MAX / sizeof(*r->interfaces)) {
		fail(r, "getifaddrs allocation size", EOVERFLOW);
		goto done;
	}
	if (count == 0) {
		fail(r, "getifaddrs returned no interfaces", ENODEV);
		goto done;
	}
	r->interfaces = calloc(count, sizeof(*r->interfaces));
	if (!r->interfaces) {
		fail(r, "calloc(interface list)", ENOMEM);
		goto done;
	}
	for (struct ifaddrs *item = list; item; item = item->ifa_next) {
		struct app_network_interface *out = &r->interfaces[r->interface_count++];
		const char *name = item->ifa_name ? item->ifa_name : "";
		if (strlen(name) >= sizeof(out->name)) {
			fail(r, "interface name truncation", EOVERFLOW);
			goto done;
		}
		snprintf(out->name, sizeof(out->name), "%s", name);
		out->flags = item->ifa_flags;
		out->family = item->ifa_addr ? item->ifa_addr->sa_family : AF_UNSPEC;
		out->prefix_length = -1;
		const void *address = NULL, *mask = NULL;
		size_t size = 0;
		if (out->family == AF_INET) {
			address = &((struct sockaddr_in *)item->ifa_addr)->sin_addr;
			size = sizeof(struct in_addr);
			if (item->ifa_netmask)
				mask = &((struct sockaddr_in *)item->ifa_netmask)->sin_addr;
		} else if (out->family == AF_INET6) {
			address = &((struct sockaddr_in6 *)item->ifa_addr)->sin6_addr;
			size = sizeof(struct in6_addr);
			if (item->ifa_netmask)
				mask = &((struct sockaddr_in6 *)item->ifa_netmask)->sin6_addr;
		}
		if (address) {
			if (!inet_ntop(out->family, address, out->address, sizeof(out->address))) {
				fail(r, "inet_ntop", errno);
				goto done;
			}
			if (!mask || (out->prefix_length = prefix_length(mask, size)) < 0) {
				fail(r, "missing/non-contiguous interface netmask", EINVAL);
				goto done;
			}
		}
	}
	r->passed = 1;
done:
	freeifaddrs(list);
}

struct app_network_result *
app_network_run(int operation, int timeout_ms)
{
	struct app_network_result *r = calloc(1, sizeof(*r));
	if (!r)
		return NULL;
	r->pid = (int)getpid();
	r->uid = (int)getuid();
	r->gid = (int)getgid();
	r->socket_flags = SOCK_NONBLOCK | SOCK_CLOEXEC;
	if (timeout_ms <= 0) {
		fail(r, "timeout must be positive", EINVAL);
		return r;
	}
	int64_t start = now_ms();
	if (start < 0) {
		fail(r, "clock_gettime(CLOCK_MONOTONIC)", errno);
		return r;
	}
	int64_t deadline = start + timeout_ms;
	switch (operation) {
	case APP_RAW_TCP_BIND: raw_bind(r, SOCK_STREAM); break;
	case APP_RAW_UDP_BIND: raw_bind(r, SOCK_DGRAM); break;
	case APP_RAW_UDP_BROADCAST: raw_broadcast(r); break;
	case APP_TCP_ROUNDTRIP: tcp_roundtrip(r, deadline); break;
	case APP_UDP_ROUNDTRIP: udp_roundtrip(r, deadline); break;
	case APP_GETIFADDRS: interfaces(r); break;
	default: fail(r, "unknown operation", EINVAL); break;
	}
	if (r->passed)
		snprintf(r->stage, sizeof(r->stage), "complete");
	return r;
}

void
app_network_result_free(struct app_network_result *r)
{
	if (!r)
		return;
	free(r->interfaces);
	free(r);
}
