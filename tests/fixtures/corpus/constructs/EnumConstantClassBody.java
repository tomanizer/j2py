package org.springframework.example;

/**
 * Enum constants with anonymous class bodies overriding abstract methods.
 * Pattern from caffeine RemovalCause.
 */
public enum EnumConstantClassBody {

    EXPLICIT {
        @Override
        public boolean wasEvicted() {
            return false;
        }
    },

    REPLACED {
        @Override
        public boolean wasEvicted() {
            return false;
        }
    },

    COLLECTED {
        @Override
        public boolean wasEvicted() {
            return true;
        }
    };

    public abstract boolean wasEvicted();
}
