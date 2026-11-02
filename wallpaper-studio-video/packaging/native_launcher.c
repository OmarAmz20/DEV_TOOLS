/* Tiny, statically linked launcher. No FUSE, shell evaluation or system writes. */
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <limits.h>
#include "bootstrap_code.h"

int main(int argc, char **argv) {
    char self[PATH_MAX + 1];
    ssize_t length=readlink("/proc/self/exe",self,PATH_MAX);
    if (length<0) { perror("Wallpaper Studio Video"); return 1; }
    self[length]='\0';
    char **args=calloc((size_t)argc+4,sizeof(char *));
    if (!args) return 1;
    args[0]="/usr/bin/python3";args[1]="-c";args[2]=BOOTSTRAP_CODE;args[3]=self;
    for(int i=1;i<argc;i++)args[i+3]=argv[i];
    execv(args[0],args);
    perror("Wallpaper Studio Video requires /usr/bin/python3");
    return 1;
}
