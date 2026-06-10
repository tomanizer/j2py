package org.springframework.aot.hint;

/**
 * Build-time hint registrar.
 */
public class CommentsAnnotations {

    @Override
    public void registerReflectionHints(RuntimeHints hints) {
        // register public constructors
        hints.reflection().registerType(CommentsAnnotations.class);
    }
}
