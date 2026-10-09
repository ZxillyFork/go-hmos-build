// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

#ifndef GO_HMOS_EMULATOR_NATIVE_H
#define GO_HMOS_EMULATOR_NATIVE_H

void emulatorSetTLS(int value);
int emulatorGetTLS(void);
int emulatorAdd(int a, int b);
int emulatorPthreads(void);

#endif
