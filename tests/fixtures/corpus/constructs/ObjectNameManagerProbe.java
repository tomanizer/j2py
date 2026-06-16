import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public class ObjectNameManagerProbe {
    public static ObjectName getInstance(Object name) throws MalformedObjectNameException {
        if (name instanceof ObjectName objectName) {
            return objectName;
        }
        if (name instanceof String text) {
            return getInstance(text);
        }
        throw new MalformedObjectNameException();
    }

    public static ObjectName getInstance(String objectName) throws MalformedObjectNameException {
        return ObjectName.getInstance(objectName);
    }

    public static ObjectName getInstance(String domainName, String key, String value)
            throws MalformedObjectNameException {
        return ObjectName.getInstance(domainName, key, value);
    }

    public static ObjectName getInstance(String domainName, Hashtable<String, String> properties)
            throws MalformedObjectNameException {
        return ObjectName.getInstance(domainName, properties);
    }
}
