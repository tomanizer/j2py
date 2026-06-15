package org.springframework.example;

import java.util.Calendar;
import java.util.List;
import java.util.Map;

/**
 * Non-collection API get() calls should not be treated as ambiguous collection access.
 */
public class AmbiguousGetProbe {

    public int calendarDay(Calendar calendar) {
        return calendar.get(Calendar.DAY_OF_MONTH);
    }

    public String listValue(List<String> values, int index) {
        return values.get(index);
    }

    public Object mapValue(Map<String, Object> values, String key) {
        return values.get(key);
    }
}
