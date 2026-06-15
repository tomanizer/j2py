package org.springframework.example;

import java.util.Map;

/**
 * Corpus hotspot: Spring PropertyEditorRegistrySupport uses array class literals
 * such as Class[].class and int[].class as map keys.
 */
public class CorpusArrayTypeMapProbe {

    public void registerArrayEditors(Map<Class<?>, Object> editors) {
        editors.put(Class[].class, new Object());
        editors.put(String[].class, new Object());
        editors.put(int[].class, new Object());
    }
}
