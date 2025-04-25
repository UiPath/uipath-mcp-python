import math
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Advanced Math Operations Server")


# Basic arithmetic operations
@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of a and b
    """
    return a + b


@mcp.tool()
def subtract(a: float, b: float) -> float:
    """Subtract the second number from the first.

    Args:
        a: Number to subtract from
        b: Number to subtract

    Returns:
        Difference of a and b
    """
    return a - b


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        Product of a and b
    """
    return a * b


@mcp.tool()
def divide(a: float, b: float) -> float:
    """Divide the first number by the second.

    Args:
        a: Numerator
        b: Denominator

    Returns:
        Quotient of a and b

    Raises:
        ValueError: If b is zero
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


# Power and root operations
@mcp.tool()
def power(base: float, exponent: float) -> float:
    """Calculate the base raised to the exponent power.

    Args:
        base: The base number
        exponent: The exponent

    Returns:
        The result of base^exponent
    """
    return math.pow(base, exponent)


@mcp.tool()
def square_root(number: float) -> float:
    """Calculate the square root of a number.

    Args:
        number: The number to find the square root of

    Returns:
        The square root of the number

    Raises:
        ValueError: If number is negative
    """
    if number < 0:
        raise ValueError("Cannot calculate the square root of a negative number")
    return math.sqrt(number)


@mcp.tool()
def nth_root(number: float, n: float) -> float:
    """Calculate the nth root of a number.

    Args:
        number: The number to find the root of
        n: The root value

    Returns:
        The nth root of the number

    Raises:
        ValueError: If number is negative and n is even
    """
    if number < 0 and n % 2 == 0:
        raise ValueError("Cannot calculate even root of a negative number")
    return math.pow(number, 1 / n)


# Trigonometric functions
@mcp.tool()
def sin(angle_degrees: float) -> float:
    """Calculate the sine of an angle in degrees.

    Args:
        angle_degrees: Angle in degrees

    Returns:
        Sine of the angle
    """
    return math.sin(math.radians(angle_degrees))


@mcp.tool()
def cos(angle_degrees: float) -> float:
    """Calculate the cosine of an angle in degrees.

    Args:
        angle_degrees: Angle in degrees

    Returns:
        Cosine of the angle
    """
    return math.cos(math.radians(angle_degrees))


@mcp.tool()
def tan(angle_degrees: float) -> float:
    """Calculate the tangent of an angle in degrees.

    Args:
        angle_degrees: Angle in degrees

    Returns:
        Tangent of the angle

    Raises:
        ValueError: If angle is 90 degrees + k*180 degrees (undefined tangent)
    """
    # Check for undefined tangent values
    if angle_degrees % 180 == 90:
        raise ValueError(f"Tangent is undefined at {angle_degrees} degrees")
    return math.tan(math.radians(angle_degrees))


# Logarithmic functions
@mcp.tool()
def log10(number: float) -> float:
    """Calculate the base-10 logarithm of a number.

    Args:
        number: The input number

    Returns:
        The base-10 logarithm of the number

    Raises:
        ValueError: If number is less than or equal to zero
    """
    if number <= 0:
        raise ValueError("Cannot calculate logarithm of zero or negative number")
    return math.log10(number)


@mcp.tool()
def natural_log(number: float) -> float:
    """Calculate the natural logarithm (base e) of a number.

    Args:
        number: The input number

    Returns:
        The natural logarithm of the number

    Raises:
        ValueError: If number is less than or equal to zero
    """
    if number <= 0:
        raise ValueError("Cannot calculate logarithm of zero or negative number")
    return math.log(number)


@mcp.tool()
def log_base(number: float, base: float) -> float:
    """Calculate the logarithm of a number with a custom base.

    Args:
        number: The input number
        base: The logarithm base

    Returns:
        The logarithm of the number with the specified base

    Raises:
        ValueError: If number or base is less than or equal to zero, or if base is 1
    """
    if number <= 0:
        raise ValueError("Cannot calculate logarithm of zero or negative number")
    if base <= 0:
        raise ValueError("Logarithm base must be greater than zero")
    if base == 1:
        raise ValueError("Logarithm base cannot be 1")
    return math.log(number, base)


# Statistical operations
@mcp.tool()
def mean(numbers: List[float]) -> float:
    """Calculate the arithmetic mean (average) of a list of numbers.

    Args:
        numbers: List of numbers

    Returns:
        The mean of the numbers

    Raises:
        ValueError: If the list is empty
    """
    if not numbers:
        raise ValueError("Cannot calculate mean of an empty list")
    return sum(numbers) / len(numbers)


@mcp.tool()
def median(numbers: List[float]) -> float:
    """Calculate the median of a list of numbers.

    Args:
        numbers: List of numbers

    Returns:
        The median of the numbers

    Raises:
        ValueError: If the list is empty
    """
    if not numbers:
        raise ValueError("Cannot calculate median of an empty list")

    sorted_numbers = sorted(numbers)
    n = len(sorted_numbers)

    if n % 2 == 0:
        # Even number of elements, take average of middle two
        return (sorted_numbers[n // 2 - 1] + sorted_numbers[n // 2]) / 2
    else:
        # Odd number of elements, take the middle one
        return sorted_numbers[n // 2]


@mcp.tool()
def standard_deviation(numbers: List[float], sample: bool = True) -> float:
    """Calculate the standard deviation of a list of numbers.

    Args:
        numbers: List of numbers
        sample: If True, calculate sample standard deviation, otherwise population

    Returns:
        The standard deviation of the numbers

    Raises:
        ValueError: If the list is empty or has only one element for sample calculation
    """
    if not numbers:
        raise ValueError("Cannot calculate standard deviation of an empty list")

    n = len(numbers)

    if sample and n <= 1:
        raise ValueError("Sample standard deviation requires at least two values")

    avg = sum(numbers) / n
    variance = sum((x - avg) ** 2 for x in numbers)

    if sample:
        # Sample standard deviation (Bessel's correction)
        return math.sqrt(variance / (n - 1))
    else:
        # Population standard deviation
        return math.sqrt(variance / n)


# Complex number operations
@mcp.tool()
def complex_add(
    a_real: float, a_imag: float, b_real: float, b_imag: float
) -> Dict[str, float]:
    """Add two complex numbers.

    Args:
        a_real: Real part of first complex number
        a_imag: Imaginary part of first complex number
        b_real: Real part of second complex number
        b_imag: Imaginary part of second complex number

    Returns:
        Dictionary with real and imaginary parts of the result
    """
    return {"real": a_real + b_real, "imaginary": a_imag + b_imag}


@mcp.tool()
def complex_multiply(
    a_real: float, a_imag: float, b_real: float, b_imag: float
) -> Dict[str, float]:
    """Multiply two complex numbers.

    Args:
        a_real: Real part of first complex number
        a_imag: Imaginary part of first complex number
        b_real: Real part of second complex number
        b_imag: Imaginary part of second complex number

    Returns:
        Dictionary with real and imaginary parts of the result
    """
    real_part = a_real * b_real - a_imag * b_imag
    imag_part = a_real * b_imag + a_imag * b_real

    return {"real": real_part, "imaginary": imag_part}


# Unit conversion tools
@mcp.tool()
def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Convert temperature between Celsius, Fahrenheit, and Kelvin.

    Args:
        value: The temperature value to convert
        from_unit: The source unit ('celsius', 'fahrenheit', or 'kelvin')
        to_unit: The target unit ('celsius', 'fahrenheit', or 'kelvin')

    Returns:
        The converted temperature value

    Raises:
        ValueError: If units are not recognized
    """
    from_unit = from_unit.lower()
    to_unit = to_unit.lower()

    valid_units = {"celsius", "fahrenheit", "kelvin"}
    if from_unit not in valid_units or to_unit not in valid_units:
        raise ValueError(f"Units must be one of: {', '.join(valid_units)}")

    # Convert to Celsius first (as intermediate step)
    if from_unit == "celsius":
        celsius = value
    elif from_unit == "fahrenheit":
        celsius = (value - 32) * 5 / 9
    else:  # kelvin
        celsius = value - 273.15

    # Convert from Celsius to target unit
    if to_unit == "celsius":
        return celsius
    elif to_unit == "fahrenheit":
        return celsius * 9 / 5 + 32
    else:  # kelvin
        return celsius + 273.15


@mcp.tool()
def solve_quadratic(a: float, b: float, c: float) -> Dict[str, Any]:
    """Solve a quadratic equation of the form ax² + bx + c = 0.

    Args:
        a: Coefficient of x²
        b: Coefficient of x
        c: Constant term

    Returns:
        Dictionary with solution information

    Raises:
        ValueError: If a is zero (not a quadratic equation)
    """
    if a == 0:
        raise ValueError("Coefficient 'a' cannot be zero for a quadratic equation")

    discriminant = b**2 - 4 * a * c

    result = {"discriminant": discriminant, "equation": f"{a}x² + {b}x + {c} = 0"}

    if discriminant > 0:
        # Two real solutions
        x1 = (-b + math.sqrt(discriminant)) / (2 * a)
        x2 = (-b - math.sqrt(discriminant)) / (2 * a)
        result["solution_type"] = "two real solutions"
        result["solutions"] = [x1, x2]
    elif discriminant == 0:
        # One real solution (repeated)
        x = -b / (2 * a)
        result["solution_type"] = "one real solution (repeated)"
        result["solutions"] = [x]
    else:
        # Complex solutions
        real_part = -b / (2 * a)
        imag_part = math.sqrt(abs(discriminant)) / (2 * a)
        result["solution_type"] = "two complex solutions"
        result["solutions"] = [
            {"real": real_part, "imaginary": imag_part},
            {"real": real_part, "imaginary": -imag_part},
        ]

    return result


# Constants
@mcp.tool()
def get_constants() -> Dict[str, float]:
    """Return a dictionary of common mathematical constants.

    Returns:
        Dictionary of mathematical constants with their values
    """
    return {
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,  # 2π
        "phi": (1 + math.sqrt(5)) / 2,  # Golden ratio
        "euler_mascheroni": 0.57721566490153286,
        "sqrt2": math.sqrt(2),
        "sqrt3": math.sqrt(3),
        "ln2": math.log(2),
        "ln10": math.log(10),
    }


# Run the server when the script is executed
if __name__ == "__main__":
    mcp.run()
