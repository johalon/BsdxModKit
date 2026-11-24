package lombok;
import java.lang.annotation.*;
@Retention(RetentionPolicy.SOURCE) public @interface EqualsAndHashCode { boolean callSuper() default false; String[] exclude() default {}; String staticName() default ""; AccessLevel value() default AccessLevel.PUBLIC; }
