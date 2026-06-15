package com.fasterxml.jackson.example;

/**
 * Corpus hotspot: Jackson InetSocketAddressSerializer has a nested string
 * concatenation ternary that was reported as malformed.
 */
public class CorpusMalformedTernaryProbe {

    public String bracketHost(Object addr, String str) {
        int ix = str.indexOf("/");
        if (ix == 0) {
            str = addr instanceof Object
                    ? "[" + str.substring(1) + "]"
                    : str.substring(1);
        }
        return str;
    }
}
