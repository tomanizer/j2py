package com.google.common.example;

import static java.lang.annotation.ElementType.CONSTRUCTOR;
import static java.lang.annotation.ElementType.METHOD;
import static java.lang.annotation.ElementType.TYPE;

import java.lang.annotation.Target;

/**
 * Corpus hotspot: Guava IgnoreJRERequirement imports ElementType enum constants
 * statically and uses them inside @Target.
 */
@Target({METHOD, CONSTRUCTOR, TYPE})
public @interface StaticImportEnumConstants {
}
