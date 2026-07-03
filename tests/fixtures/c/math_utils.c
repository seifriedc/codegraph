#include <math.h>
#include <stdlib.h>

typedef struct {
    double x;
    double y;
} Point;

double distance(Point a, Point b) {
    double dx = b.x - a.x;
    double dy = b.y - a.y;
    return sqrt(dx * dx + dy * dy);
}

double dot_product(Point a, Point b) {
    return a.x * b.x + a.y * b.y;
}

Point* make_point(double x, double y) {
    Point* p = malloc(sizeof(Point));
    p->x = x;
    p->y = y;
    return p;
}
