// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license in LICENSE.
#ifndef __OHOS__
#error expected OpenHarmony SDK compiler
#endif
#include <napi/native_api.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct work {
    napi_async_work async;
    napi_deferred promise;
    char token[33];
    char *result;
    char error[512];
};

static void execute(napi_env env, void *data)
{
    (void)env;
    struct work *w = data;
    // Set before loading Go, exactly as the pinned core dlopen fixture expects.
    if (setenv("OHOS_GO_TEST", "before-dlopen", 1) != 0) {
        snprintf(w->error, sizeof(w->error), "setenv failed");
        return;
    }
    void *handle = dlopen("libgo_app_network.so", RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
        snprintf(w->error, sizeof(w->error), "dlopen: %s", dlerror());
        return;
    }
    char *(*check)(void) = (char *(*)(void))dlsym(handle, "GoAppNetworkCheck");
    void (*release)(char *) = (void (*)(char *))dlsym(handle, "GoAppNetworkFree");
    if (!check || !release) {
        snprintf(w->error, sizeof(w->error), "required Go exports missing");
        return;
    }
    char *report = check();
    if (!report) {
        snprintf(w->error, sizeof(w->error), "Go returned null report");
        return;
    }
    size_t length = strlen(report) + 96;
    w->result = malloc(length);
    if (w->result) {
        snprintf(w->result, length, "{\"token\":\"%s\",\"report\":%s}", w->token, report);
    } else {
        snprintf(w->error, sizeof(w->error), "report allocation failed");
    }
    release(report);
    // Do not dlclose Go: its runtime has threads which outlive this call.
}

static void complete(napi_env env, napi_status status, void *data)
{
    struct work *w = data;
    napi_value value;
    if (status == napi_ok && w->result) {
        if (napi_create_string_utf8(env, w->result, NAPI_AUTO_LENGTH, &value) == napi_ok)
            napi_resolve_deferred(env, w->promise, value);
    } else {
        napi_value message;
        const char *error = w->error[0] ? w->error : "native async work failed";
        napi_create_string_utf8(env, error, NAPI_AUTO_LENGTH, &message);
        napi_create_error(env, NULL, message, &value);
        napi_reject_deferred(env, w->promise, value);
    }
    free(w->result);
    napi_delete_async_work(env, w->async);
    free(w);
}

static napi_value run(napi_env env, napi_callback_info info)
{
    static int started;
    size_t argc = 1, length = 0;
    napi_value argv[1], promise, resource;
    struct work *w = calloc(1, sizeof(*w));
    if (!w) {
        napi_throw_error(env, NULL, "out of memory");
        return NULL;
    }
    if (napi_get_cb_info(env, info, &argc, argv, NULL, NULL) != napi_ok || argc != 1 ||
        napi_get_value_string_utf8(env, argv[0], w->token, sizeof(w->token), &length) != napi_ok ||
        length != 32 || strspn(w->token, "0123456789abcdef") != 32 || started) {
        free(w);
        napi_throw_error(env, NULL, "expected fresh invocation and 32-character hex token");
        return NULL;
    }
    if (napi_create_promise(env, &w->promise, &promise) != napi_ok ||
        napi_create_string_utf8(env, "GoHmosNetworkCheck", NAPI_AUTO_LENGTH, &resource) != napi_ok ||
        napi_create_async_work(env, NULL, resource, execute, complete, w, &w->async) != napi_ok) {
        free(w);
        napi_throw_error(env, NULL, "cannot create native async work");
        return NULL;
    }
    if (napi_queue_async_work(env, w->async) != napi_ok) {
        napi_delete_async_work(env, w->async);
        free(w);
        napi_throw_error(env, NULL, "cannot queue native async work");
        return NULL;
    }
    started = 1;
    return promise;
}

static napi_value init(napi_env env, napi_value exports)
{
    napi_property_descriptor descriptor = {
        .utf8name = "run", .method = run, .attributes = napi_default
    };
    if (napi_define_properties(env, exports, 1, &descriptor) != napi_ok)
        return NULL;
    return exports;
}

static napi_module module = {
    .nm_version = 1, .nm_register_func = init, .nm_modname = "gohmos"
};
__attribute__((constructor)) static void register_module(void)
{
    napi_module_register(&module);
}
