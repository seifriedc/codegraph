with Ada.Numerics.Elementary_Functions;

package body Geometry is

   function Distance (A, B : Point) return Float is
      Dx : Float := B.X - A.X;
      Dy : Float := B.Y - A.Y;
   begin
      return Ada.Numerics.Elementary_Functions.Sqrt (Dx * Dx + Dy * Dy);
   end Distance;

   procedure Translate (P : in out Point; Dx, Dy : Float) is
   begin
      P.X := P.X + Dx;
      P.Y := P.Y + Dy;
   end Translate;

end Geometry;
