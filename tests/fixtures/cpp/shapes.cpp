#include <cmath>
#include <string>

struct Point {
    double x;
    double y;
};

class Shape {
public:
    virtual double area() const = 0;
    virtual std::string name() const = 0;
};

class Circle : public Shape {
public:
    explicit Circle(Point center, double radius)
        : center_(center), radius_(radius) {}

    double area() const override {
        return M_PI * radius_ * radius_;
    }

    std::string name() const override {
        return "Circle";
    }

    double radius() const { return radius_; }

private:
    Point center_;
    double radius_;
};

class Rectangle : public Shape {
public:
    Rectangle(double width, double height)
        : width_(width), height_(height) {}

    double area() const override {
        return width_ * height_;
    }

    std::string name() const override {
        return "Rectangle";
    }

private:
    double width_;
    double height_;
};

double total_area(Shape** shapes, int count) {
    double total = 0.0;
    for (int i = 0; i < count; ++i) {
        total += shapes[i]->area();
    }
    return total;
}
