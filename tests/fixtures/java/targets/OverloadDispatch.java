package org.springframework.aot.hint;

import java.util.function.Consumer;

// Modeled on org.springframework.aot.hint.ReflectionHints.registerType: same
// arity, different parameter types, genuinely different bodies. Not mergeable;
// requires runtime dispatch (ADR 0009).
public class OverloadDispatch {

    public OverloadDispatch registerType(TypeReference type, Consumer<Builder> typeHint) {
        typeHint.accept(new Builder(type));
        return this;
    }

    public OverloadDispatch registerType(Class<?> type, MemberCategory... memberCategories) {
        return registerType(TypeReference.of(type), TypeHint.builtWith(memberCategories));
    }
}

// Modeled on org.springframework.aot.generate.DefaultGenerationContext: a
// delegating constructor, an implementation constructor, and a copy
// constructor that collides on arity with the first.
class DispatchContext {

    private final String name;
    private final RuntimeHints runtimeHints;

    DispatchContext(String name, GeneratedFiles generatedFiles) {
        this(name, generatedFiles, new RuntimeHints());
    }

    DispatchContext(String name, GeneratedFiles generatedFiles, RuntimeHints runtimeHints) {
        this.name = name;
        this.runtimeHints = runtimeHints;
    }

    DispatchContext(DispatchContext existing, String featureName) {
        this.name = existing.name + featureName;
        this.runtimeHints = existing.runtimeHints;
    }
}
