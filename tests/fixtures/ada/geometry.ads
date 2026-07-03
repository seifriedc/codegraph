with Ada.Numerics;

package Geometry is

   type Point is record
      X, Y : Float;
   end record;

   type Shape is tagged record
      Color : String (1 .. 10);
   end record;

   type Circle is new Shape with record
      Center : Point;
      Radius : Float;
   end record;

   function Distance (A, B : Point) return Float;
   procedure Translate (P : in out Point; Dx, Dy : Float);

end Geometry;
