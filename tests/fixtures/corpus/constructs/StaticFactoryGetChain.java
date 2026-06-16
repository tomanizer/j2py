package org.springframework.example;

import java.lang.annotation.Annotation;

/**
 * Static factory return types should disambiguate chained get() API calls.
 */
public class StaticFactoryGetChain {
    public Object lookup(Annotation annotation, Class<?> annotationType) {
        return MergedAnnotations.from(annotation).get(annotationType);
    }

    static class MergedAnnotations {
        static MergedAnnotations from(Annotation annotation) {
            return new MergedAnnotations();
        }

        MergedAnnotation get(Class<?> annotationType) {
            return new MergedAnnotation();
        }
    }

    static class MergedAnnotation {
    }
}
