@RestController
public class SpringAnnotationPreset {
    @GetMapping("/hello")
    public String hello() {
        return "ok";
    }
}
