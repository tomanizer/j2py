package org.springframework.core.io;

import java.io.IOException;

public class Exceptions {

    public String read(Resource resource) throws IOException {
        try {
            return resource.getContentAsString();
        }
        catch (IOException ex) {
            throw new IllegalStateException("Failed to read", ex);
        }
        finally {
            resource.close();
        }
    }
}
