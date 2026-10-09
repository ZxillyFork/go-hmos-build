#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <ifaddrs.h>
#include <netdb.h>
#include <pwd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

struct config { int32_t error, timeout; uint32_t retry, nonpublic; char servers[5][51]; };
int main(void) {
    time_t epoch = 1700000000;
    struct tm local;
    localtime_r(&epoch, &local);
    printf("offset=%ld\nzone=%s\n", local.tm_gmtoff, local.tm_zone);
    void *lib = dlopen("libnetsys_client.z.so", RTLD_NOW);
    int32_t (*getconfig)(uint16_t, struct config *) = lib ? dlsym(lib, "NetSysGetResolvConf") : NULL;
    struct config cfg = {0};
    int ret = getconfig ? getconfig(0, &cfg) : -9999;
    printf("dns_status=%d\ndns_error=%d\n", ret, cfg.error);
    for (int i=0; i<5; i++) if (cfg.servers[i][0]) printf("dns_server=%s\n", cfg.servers[i]);
    struct addrinfo *answer = NULL;
    ret = getaddrinfo("example.com", NULL, NULL, &answer);
    printf("lookup_status=%d\n", ret);
    if (answer) freeaddrinfo(answer);
    struct ifaddrs *list = NULL;
    ret = getifaddrs(&list);
    printf("interfaces_status=%d\ninterfaces_errno=%d\n", ret, errno);
    if (!ret) {
        for (struct ifaddrs *item=list; item; item=item->ifa_next) printf("interface=%s\n", item->ifa_name);
        freeifaddrs(list);
    }
    struct passwd *pw = getpwuid(getuid());
    if (pw) printf("username=%s\nhome=%s\n", pw->pw_name, pw->pw_dir);
    else printf("user_errno=%d\n", errno);
    return 0;
}
