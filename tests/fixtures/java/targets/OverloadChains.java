package org.springframework.aot.generate;

import java.util.HashMap;
import java.util.Map;

// Modeled on org.springframework.aot.generate.ClassNameGenerator: chained
// this(...) constructor delegation plus a builder-style forwarding method.
public class OverloadChains {

    private final String defaultTarget;
    private final String featureNamePrefix;
    private final Map<String, Integer> sequenceGenerator;

    public OverloadChains(String defaultTarget) {
        this(defaultTarget, "");
    }

    public OverloadChains(String defaultTarget, String featureNamePrefix) {
        this(defaultTarget, featureNamePrefix, new HashMap<>());
    }

    private OverloadChains(String defaultTarget, String featureNamePrefix,
            Map<String, Integer> sequenceGenerator) {
        this.defaultTarget = defaultTarget;
        this.featureNamePrefix = featureNamePrefix;
        this.sequenceGenerator = sequenceGenerator;
    }

    public String generate(String name) {
        return generate(name, "-");
    }

    public String generate(String name, String separator) {
        return this.featureNamePrefix + separator + name;
    }
}
