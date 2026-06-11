package org.springframework.core.io;

import java.io.IOException;

public class TryWithResources {

    public String read(ResourceFactory factory) throws IOException {
        try (Resource resource = factory.open()) {
            return resource.read();
        }
    }
}
