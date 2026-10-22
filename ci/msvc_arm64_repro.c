/* Reduced from HDF5 2.2.0 src/H5Tinit_float.c, DETECT_F padding detection.
 * Copyright 2006 by The HDF Group.
 * Copyright 1998-2006 by The Board of Trustees of the University of Illinois.
 * All rights reserved. See msvc_arm64_repro.LICENSE for terms.
 */
#include <string.h>

void detect(unsigned char *out)
{
    double value = 4.0, changed;
    unsigned char bytes[sizeof(double)];
    unsigned char mask[sizeof(double)] = {0};

    memcpy(bytes, &value, sizeof(value));
    for (int i = 0; i < sizeof(double); ++i) {
        for (unsigned char bit = 1; bit; bit = (unsigned char)(bit << 1)) {
            bytes[i] ^= bit;
            memcpy(&changed, bytes, sizeof(changed));
            if (value != changed)
                mask[i] |= bit;
            bytes[i] ^= bit;
        }
    }
    memcpy(out, mask, sizeof(mask));
}
