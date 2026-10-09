// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

#ifndef GO_HMOS_APP_NETWORK_NATIVE_H
#define GO_HMOS_APP_NETWORK_NATIVE_H

#include <stddef.h>

enum app_network_operation {
	APP_RAW_TCP_BIND,
	APP_RAW_UDP_BIND,
	APP_RAW_UDP_BROADCAST,
	APP_TCP_ROUNDTRIP,
	APP_UDP_ROUNDTRIP,
	APP_GETIFADDRS
};

struct app_network_interface {
	char name[256];
	char address[64];
	unsigned int flags;
	int family;
	int prefix_length;
};

struct app_network_result {
	int passed;
	int error_number;
	int pid;
	int uid;
	int gid;
	int socket_flags;
	char stage[96];
	char error_text[256];
	size_t interface_count;
	struct app_network_interface *interfaces;
};

// All socket operations run in the calling app process. Native round trips use
// nonblocking sockets plus one CLOCK_MONOTONIC deadline for the entire exchange.
// The caller also enforces a deadline, including for libc getifaddrs.
struct app_network_result *app_network_run(int operation, int timeout_ms);
void app_network_result_free(struct app_network_result *result);

#endif
