package lombok;
import java.lang.annotation.*;
@Retention(RetentionPolicy.SOURCE) public @interface Data { boolean callSuper() default false; String[] exclude() default {}; String staticName() default ""; AccessLevel value() default AccessLevel.PUBLIC; }
